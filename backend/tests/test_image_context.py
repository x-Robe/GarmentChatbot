"""Offline client vector, reuse, continuation and HTTP contract tests."""
import json, os, unittest
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image
from pydantic import ValidationError
from fastapi.testclient import TestClient
import api
from src.image_reference import ImageReference, ImageActiveSearch
from src.product_search import ProductSearch
from src.query_attribute_extractor import QueryAttributeExtractor
import test_chatbot_results as fixtures
from test_hybrid_image_search import attributes
from test_image_api import image_bytes

def reference():
    return dict(version=1,model=os.getenv('CLIP_MODEL'),dimension=512,embedding=[1.]+[0.]*511,image_analysis=attributes())
def active(**overrides):
    return ImageActiveSearch(text_overrides=overrides,effective_filters=overrides).model_dump()

class ReferenceTests(unittest.TestCase):
    def test_vector_validation(self):
        self.assertEqual(len(ImageReference(**reference()).embedding),512)
        for v in ([0.]*512,[1.]*512,[1.],[True]+[0.]*511,['1']+[0.]*511,[float('nan')]+[0.]*511,[float('inf')]+[0.]*511):
            with self.assertRaises(ValidationError):ImageReference(**{**reference(),'embedding':v})
    def test_version_and_analysis(self):
        for change in ({'model':'other'},{'version':True},{'version':2},{'dimension':768},{'image_analysis':{'injected':{}}},{'image_analysis':{'colors':{'label':'secret'}}}):
            with self.assertRaises(ValidationError):ImageReference(**{**reference(),**change})
        ref=reference();ref['image_analysis']['colors']['margin']=float('inf')
        with self.assertRaises(ValidationError):ImageReference(**ref)
    def test_state_validation(self):
        for change in ({'text_overrides':{'price':['cheap']}},{'shown_product_ids':['x']*4097},{'shown_point_ids':['bad']},{'text_overrides':{'colors':['black']}}):
            with self.assertRaises(ValidationError):ImageActiveSearch(**change)
    def test_http_validation(self):
        with TestClient(api.app) as c,patch.object(api,'_create_agent') as f:
            r=c.post('/api/image-search/continue',json={'query':'more','reference_image':{**reference(),'model':'secret'}})
            self.assertEqual(r.status_code,422);self.assertNotIn('secret',r.text)
            r=c.post('/api/image-search/continue',content=b' '*(2*1024*1024+1))
            self.assertEqual(r.status_code,413);f.assert_not_called()

class RetrievalTests(unittest.TestCase):
    def search(self):
        s=ProductSearch.__new__(ProductSearch);s.embedder=Mock(model_name=os.getenv('CLIP_MODEL'))
        s.embedder.embed_pil_image.return_value=np.array(reference()['embedding'],dtype=np.float32)
        s._image_classifier=Mock();s._image_classifier.analyze.return_value=attributes()
        s.client=Mock();s.client.count.return_value=NS(count=100);s.collection_name='test'
        s._query_qdrant=Mock(return_value=[NS(id=1,score=.8,payload={'product_id':1})]);return s
    def test_encode_once_reuse_same_results(self):
        s=self.search();first=s.search_by_image_hybrid(Image.new('RGB',(2,2)),limit=1)
        ref=ImageReference(**first['image_reference'])
        again=s.search_by_image_embedding(np.array(ref.embedding),ref.image_analysis,limit=1)
        self.assertEqual(first['results'],again['results']);s.embedder.embed_pil_image.assert_called_once();s._image_classifier.analyze.assert_called_once()
    def test_mixed_original_analysis_immutable(self):
        s=self.search();r=s.search_by_image_with_overrides(Image.new('RGB',(2,2)),{'colors':['white']},1)
        self.assertEqual(r['image_reference']['image_analysis'],attributes());self.assertEqual(r['image_analysis']['filters_used']['colors'],['white']);s.embedder.embed_pil_image.assert_called_once()
    def test_frozen_filters_exclude_without_reanalysis(self):
        s=self.search();s._query_text_page=Mock(return_value=[])
        r=s.search_by_image_embedding(np.array(reference()['embedding']),attributes(),overrides={'colors':['black']},excluded={'shown_product_ids':['1']},effective_filters={'colors':['black']})
        s.client.count.assert_not_called();s._image_classifier.analyze.assert_not_called();self.assertEqual(s._query_text_page.call_args.args[3],{'shown_product_ids':['1']})
    def test_upload_response_reference_no_llm(self):
        s=self.search()
        with TestClient(api.app) as c,patch.object(api,'_get_image_search',return_value=s),patch.object(api,'_create_agent') as f:
            r=c.post('/api/image-search',files={'image':('a.jpg',image_bytes(),'image/jpeg')})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['image_reference']['embedding']),512);self.assertEqual(r.json()['active_search']['shown_product_ids'],['1']);f.assert_not_called()

class ContinuationTests(unittest.TestCase):
    def agent(self,relation='image_refinement',changes=None,remove=None):
        a,_=fixtures.AgentTests().agent('none',relation=relation);a.attribute_extractor=Mock()
        a.attribute_extractor.extract_image_overrides.return_value={'intent':'modify','overrides':changes or {},'remove_overrides':remove or [],'unsupported_text':[]}
        a.product_search=Mock()
        def search(vector,analysis,overrides,limit,excluded,effective_filters,mode="auto",effective_image_strategy=None):
            n=len((excluded or {}).get('shown_product_ids',[]))+1
            return {'results':[{'product_id':str(n),'point_id':n,'attributes':{}}],'image_analysis':{'filters_used':deepcopy(overrides)}}
        a.product_search.search_by_image_embedding.side_effect=search;return a
    def test_accumulate_correct_remove_no_vector_in_llm(self):
        state=active();ref=reference();before=deepcopy(ref)
        for changes,remove,expected in [({'colors':['black']},[],{'colors':['black']}),({'sleeve':['long sleeve']},[],{'colors':['black'],'sleeve':['long sleeve']}),({'colors':['white']},[],{'colors':['white'],'sleeve':['long sleeve']}),({},['colors'],{'sleeve':['long sleeve']})]:
            a=self.agent(changes=changes,remove=remove);r=a.respond('change',active_search=state,reference_image=ref);state=r['active_search']
            self.assertEqual(state['text_overrides'],expected);self.assertEqual(state['shown_product_ids'],['1'])
            inputs=str(a.client.responses.create.call_args.kwargs['input'][1]);self.assertNotIn('embedding',inputs);self.assertNotIn('runner_up_score',inputs);self.assertEqual(ref,before)
    def test_repeated_pages_no_extraction(self):
        state=active(colors=['black'])
        for n in range(1,4):
            a=self.agent('image_more_results');r=a.respond('more',active_search=state,reference_image=reference());state=r['active_search']
            self.assertEqual(state['shown_product_ids'],[str(i) for i in range(1,n+1)]);a.attribute_extractor.extract_image_overrides.assert_not_called()
            np.testing.assert_array_equal(a.product_search.search_by_image_embedding.call_args.args[0],reference()['embedding'])
    def test_failure_does_not_mutate(self):
        a=self.agent('image_more_results');a.product_search.search_by_image_embedding.side_effect=RuntimeError('offline');state=active();before=deepcopy(state)
        with self.assertRaises(RuntimeError):a.respond('more',active_search=state,reference_image=reference())
        self.assertEqual(state,before)
    def test_independent_text_qa_domain(self):
        for intent,relation,strategy in [('search','new_topic','similar'),('informational','fashion_information','none'),('unrelated','out_of_domain','none')]:
            a,_=fixtures.AgentTests().agent(strategy,intent=intent,relation=relation);a.product_search=Mock()
            a.respond('new question',active_search=active(),reference_image=reference());a.product_search.search_by_image_embedding.assert_not_called()
    def test_restart_new_instance_same_client_reference(self):
        body={'query':'black','reference_image':reference(),'active_search':active()}
        with TestClient(api.app) as c:
            for _ in range(2):
                with patch.object(api,'_agent',self.agent(changes={'colors':['black']})):
                    r=c.post('/api/image-search/continue',json=body);self.assertEqual(r.status_code,200);self.assertEqual(r.json()['text_overrides'],{'colors':['black']})
    def test_extractor_removal(self):
        e=QueryAttributeExtractor.__new__(QueryAttributeExtractor);e.model='mock';e.client=Mock()
        values={k:None if k=='buttons' else [] for k in attributes()}
        e.client.responses.create.return_value=NS(output_text=json.dumps({'intent':'modify','overrides':values,'unsupported_text':[],'remove_overrides':['colors']}))
        r=e.extract_image_overrides('remove color requirement',allow_removal=True);self.assertEqual(r['remove_overrides'],['colors']);self.assertEqual(r['intent'],'modify')

    def test_exhaustion_no_fabricated_products(self):
        a=self.agent('image_more_results')
        a.product_search.search_by_image_embedding.side_effect=None
        a.product_search.search_by_image_embedding.return_value={'results':[], 'image_analysis':{'filters_used':{}}}
        result=a.respond('more',active_search=active(),reference_image=reference())
        self.assertEqual(result['products'],[]);self.assertIs(result['has_more'],False)

    def test_unsupported_keeps_overrides_without_retrieval(self):
        a=self.agent();a.attribute_extractor.extract_image_overrides.return_value={'intent':'unsupported','overrides':{},'unsupported_text':['futuristic']}
        before=active(colors=['black'])
        result=a.respond('futuristic',active_search=before,reference_image=reference())
        self.assertEqual(result['intent'],'clarification');self.assertEqual(result['active_search'],before)
        a.product_search.search_by_image_embedding.assert_not_called()
