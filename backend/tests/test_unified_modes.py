"""Unified image mode contracts: local Qdrant + mocked encoder/LLM, no paid calls."""
import json, os, unittest
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
import api
from src.product_search import ProductSearch
from src.image_reference import ImageActiveSearch
from src.hybrid_image_search import retrieve_hybrid
from test_hybrid_image_search import attributes
from test_image_api import image_bytes
from test_image_context import reference
import test_chatbot_results as fixtures


def predictions():
    result=attributes(colors=.1,patterns=.08,sleeve=.06)
    result['colors'].update(label='white',runner_up='black')
    result['sleeve'].update(label='short sleeve',runner_up='long sleeve')
    return result


class UnifiedModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client=QdrantClient(':memory:')
        cls.client.create_collection('unified',vectors_config=models.VectorParams(size=512,distance=models.Distance.COSINE))
        cls.client.upsert('unified',points=[models.PointStruct(id=i,vector=[1.,i*.01]+[0.]*510,
            payload={'product_id':i,'colors':[color],'patterns':[pattern],'sleeve':[sleeve],
                     'image_url':f'data/images/tshirt/{i}.jpg'})
            for i,color,pattern,sleeve in [(1,'white','plain','short sleeve'),(2,'black','plain','short sleeve'),
                (3,'black','graphic print','long sleeve'),(4,'black','plain','long sleeve'),(5,'white','plain','long sleeve')]])
    @classmethod
    def tearDownClass(cls): cls.client.close()
    def setUp(self):
        self.search=ProductSearch.__new__(ProductSearch)
        self.search.collection_name='unified';self.search.client=self.client
        self.search.embedder=Mock(model_name=os.getenv('CLIP_MODEL'))
        self.vector=np.array([1.]+[0.]*511,dtype=np.float32)
        self.search.embedder.embed_pil_image.return_value=self.vector
        self.search._image_classifier=Mock();self.search._image_classifier.analyze.return_value=predictions()
        self.search._query_qdrant=Mock(wraps=self.search._query_qdrant)
        self.search._query_text_page=Mock(wraps=self.search._query_text_page)
    def retrieve(self,mode='auto',overrides=None,limit=5,**kwargs):
        return self.search.search_by_image_embedding(self.vector,predictions(),mode=mode,overrides=overrides,limit=limit,**kwargs)
    def test_auto_matches_existing_policy_and_default(self):
        points,analysis,_=retrieve_hybrid(self.vector,predictions(),5,
            lambda f:self.client.count('unified',count_filter=f,exact=True).count,
            lambda v,f,n:self.search._query_qdrant(v,f,n),self.search._build_filter)
        result=self.retrieve()
        self.assertEqual(result['image_analysis'],analysis)
        self.assertEqual([p['point_id'] for p in result['results']],[str(p.id) for p in points])
        self.assertEqual(result['effective_image_strategy'],'pure_image_similarity')
    def test_exact_strict_top_two_no_candidate_count_or_relaxation(self):
        result=self.retrieve('exact')
        self.assertEqual(result['image_analysis']['filters_used'],{'colors':'white','patterns':'plain'})
        self.assertEqual([p['product_id'] for p in result['results']],[1,5])
        self.assertEqual(result['effective_image_strategy'],'strict_attributes')
        self.search._query_qdrant.assert_called_once()
    def test_similar_no_inferred_filters_and_order(self):
        result=self.retrieve('similar')
        self.assertEqual(result['image_analysis']['filters_used'],{})
        self.assertEqual([p['product_id'] for p in result['results']],[1,2,3,4,5])
        self.assertIsNone(self.search._query_qdrant.call_args.kwargs['query_filter'])
    def test_explicit_overrides_mandatory_for_all_modes(self):
        for mode in ('auto','exact','similar'):
            with self.subTest(mode=mode):
                result=self.retrieve(mode,{'colors':['black']})
                self.assertEqual(result['image_analysis']['filters_used']['colors'],['black'])
                self.assertTrue(result['results'])
                self.assertTrue(all(p['attributes']['colors']==['black'] for p in result['results']))
                if mode=='similar':self.assertEqual(result['image_analysis']['filters_used'],{'colors':['black']})
    def test_exact_overrides_win_but_other_reliable_image_filters_stay(self):
        r=self.retrieve('exact',{'colors':['black']})
        self.assertEqual(r['image_analysis']['filters_used'],{'colors':['black'],'patterns':'plain','sleeve':'short sleeve'})
        self.assertEqual([p['product_id'] for p in r['results']],[2])
    def test_exact_zero_does_not_broaden(self):
        r=self.retrieve('exact',{'patterns':['floral']})
        self.assertEqual(r['results'],[]);self.assertEqual(r['effective_image_strategy'],'strict_attributes')
        self.search._query_qdrant.assert_called_once()
    def test_exact_no_reliable_attributes_no_query_and_explicit_only_works(self):
        r=self.search.search_by_image_embedding(self.vector,attributes(),mode='exact')
        self.assertEqual(r['results'],[]);self.assertEqual(r['effective_image_strategy'],'attributes_required')
        self.search._query_qdrant.assert_not_called()
        r=self.search.search_by_image_embedding(self.vector,{},mode='exact',overrides={'colors':['black']})
        self.assertEqual(len(r['results']),3)
    def test_boolean_and_existing_reliability_thresholds(self):
        p=attributes(style=.039,buttons=.05,neckline=.014)
        p['buttons'].update(label='without visible buttons',runner_up='with visible buttons')
        r=self.search.search_by_image_embedding(self.vector,p,mode='exact')
        self.assertEqual(r['image_analysis']['filters_used'],{'buttons':False})
    def test_frozen_similar_cannot_accept_inferred_or_drop_mandatory(self):
        for filters in ({'colors':'white'},{'patterns':'plain'}):
            with self.assertRaises(ValueError):self.retrieve('similar',{'colors':['black']},effective_filters=filters)
    def test_original_analysis_immutable_and_upload_encodes_once(self):
        p=predictions();before=deepcopy(p)
        self.search.search_by_image_embedding(self.vector,p,mode='exact',overrides={'colors':['black']})
        self.assertEqual(p,before)
        for mode in ('auto','exact','similar'):
            self.search.embedder.reset_mock()
            self.search.search_by_image_hybrid(Image.new('RGB',(2,2)),mode=mode)
            self.search.embedder.embed_pil_image.assert_called_once()
    def test_no_classifier_still_exact_clarifies_similar_retrieves_auto_falls_back(self):
        self.search._image_classifier.analyze.side_effect=RuntimeError('unavailable')
        for mode,expected in [('auto','pure_image_similarity'),('similar','pure_image_similarity'),('exact','attributes_required')]:
            r=self.search.search_by_image_hybrid(Image.new('RGB',(2,2)),mode=mode)
            self.assertEqual(r['effective_image_strategy'],expected)

    def post(self,client,mode=None,query=''):
        data={'query':query}
        if mode is not None:data['mode']=mode
        return client.post('/api/image-search',files={'image':('a.jpg',image_bytes(),'image/jpeg')},data=data)
    def test_upload_modes_and_old_omitted_mode(self):
        with TestClient(api.app) as c,patch.object(api,'_get_image_search',return_value=self.search):
            for mode in (None,'auto','exact','similar'):
                r=self.post(c,mode);self.assertEqual(r.status_code,200)
                body=r.json();self.assertEqual(body['effective_mode'],mode or 'auto')
                self.assertEqual(body['active_search']['mode'],mode or 'auto')
                self.assertEqual(body['products'][0]['match_type'],'exact' if mode=='exact' else 'similar')
            self.assertEqual(self.post(c,'bad').status_code,422)
    def test_mixed_modes_counts_unsupported_and_partial(self):
        extractor=Mock()
        with TestClient(api.app) as c,patch.object(api,'_get_image_search',return_value=self.search),patch.object(api,'_get_override_extractor',return_value=extractor):
            for mode in ('auto','exact','similar'):
                for count in (1,3,7,12):
                    extractor.extract_image_overrides.return_value={'intent':'modify','overrides':{'colors':['black']},'unsupported_text':['futuristic'],'result_count':count}
                    r=self.post(c,mode,'show shirts and make it black and futuristic');self.assertEqual(r.status_code,200)
                    body=r.json();self.assertLessEqual(len(body['products']),min(count,8));self.assertEqual(body['effective_count'],min(count,8))
                    self.assertIn('not applied',body['text']);self.assertEqual(body['image_analysis']['filters_used']['colors'],['black'])
            extractor.extract_image_overrides.return_value={'intent':'unsupported','overrides':{},'unsupported_text':['futuristic']}
            self.search.embedder.reset_mock();body=self.post(c,'similar','futuristic').json()
            self.assertEqual(body['products'],[]);self.assertEqual(body['requested_mode'],'similar');self.search.embedder.embed_pil_image.assert_not_called()
    def test_exact_empty_attribute_http_keeps_reference_for_followup(self):
        self.search._image_classifier.analyze.return_value={}
        with TestClient(api.app) as c,patch.object(api,'_get_image_search',return_value=self.search):body=self.post(c,'exact').json()
        self.assertEqual(body['intent'],'clarification');self.assertEqual(body['effective_image_strategy'],'attributes_required')
        self.assertIsNotNone(body['image_reference']);self.assertIn('explicit attribute',body['text'])
    def agent(self,relation,changes=None,count=None):
        a,_=fixtures.AgentTests().agent('none',relation=relation,count=count)
        a.product_search=self.search;a.attribute_extractor=Mock()
        a.attribute_extractor.extract_image_overrides.return_value={'intent':'modify','overrides':changes or {},'remove_overrides':[],'unsupported_text':[]}
        return a
    def test_refinement_current_mode_accumulates_and_resets_shown(self):
        old=ImageActiveSearch(mode='auto',text_overrides={'colors':['black']},effective_filters={'colors':['black']},shown_product_ids=['3']).model_dump()
        ref={**reference(),'image_analysis':predictions()};before=deepcopy(ref)
        a=self.agent('image_refinement',{'sleeve':['long sleeve']})
        r=a.respond('make it long sleeve',mode='similar',active_search=old,reference_image=ref)
        self.assertEqual(r['effective_mode'],'similar');self.assertEqual(r['active_search']['text_overrides'],{'colors':['black'],'sleeve':['long sleeve']})
        self.assertEqual(r['active_search']['shown_product_ids'],['3','4'])
        self.assertEqual(self.search._query_text_page.call_args.args[3],None)
        self.search.embedder.embed_pil_image.assert_not_called();self.assertEqual(ref,before)
    def test_pagination_frozen_mode_filters_vector_and_exclusions(self):
        for mode,filters,strategy in [('similar',{},'pure_image_similarity'),('exact',{'colors':'white','patterns':'plain'},'strict_attributes'),('auto',{'colors':'white'},'attribute_guided')]:
            state=ImageActiveSearch(mode=mode,effective_image_strategy=strategy,effective_filters=filters,shown_product_ids=['1'],shown_point_ids=['1']).model_dump()
            a=self.agent('image_more_results',count=3)
            r=a.respond('show me 3 more',mode='exact' if mode!='exact' else 'similar',active_search=state,reference_image={**reference(),'image_analysis':predictions()})
            self.assertEqual(r['effective_mode'],mode);self.assertEqual(r['effective_image_strategy'],strategy);self.assertEqual(r['active_search']['effective_filters'],filters)
            self.assertNotIn('1',[str(p['product_id']) for p in r['products']]);self.assertLessEqual(len(r['products']),3)
            self.assertEqual(r['effective_count'],3);a.attribute_extractor.extract_image_overrides.assert_not_called()
            np.testing.assert_array_equal(self.search._query_text_page.call_args.args[0],self.vector)
    def test_old_state_defaults_auto_and_preserves_frozen_conditions(self):
        old={'search_type':'image','text_overrides':{},'effective_filters':{'colors':'white'},'shown_product_ids':[],'shown_point_ids':[]}
        r=self.agent('image_more_results').respond('more',mode='similar',active_search=old,reference_image=reference())
        self.assertEqual(r['effective_mode'],'auto');self.assertEqual(r['active_search']['effective_filters'],{'colors':'white'})
    def test_new_upload_resets_prior_image_overrides(self):
        with TestClient(api.app) as c,patch.object(api,'_get_image_search',return_value=self.search):
            first=self.post(c,'exact').json();again=self.post(c,'similar').json()
        self.assertEqual(again['active_search']['mode'],'similar');self.assertEqual(again['active_search']['text_overrides'],{})
        self.assertEqual(again['active_search']['effective_filters'],{})
        self.assertEqual(len(again['active_search']['shown_product_ids']),len(again['products']))

if __name__=='__main__':unittest.main()
