import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import api
from src.query_attribute_extractor import QueryAttributeExtractor
from src.zero_shot_classifier import ATTRIBUTE_LABELS
from src.hybrid_image_search import retrieve_hybrid
from src.product_search import ProductSearch
from test_hybrid_image_search import attributes
from test_image_api import image_bytes

class MandatoryTests(unittest.TestCase):
    def policy(self, counts, query, overrides=None):
        return retrieve_hybrid(np.array([1.,0.]),attributes(colors=.1,patterns=.08,sleeve=.06),8,
            Mock(side_effect=counts),query,deepcopy,mandatory=overrides or {'colors':['black']})

    def test_small_pool_keeps_text_order(self):
        query=Mock(return_value=['b','a']); expected={'colors':['black'],'sleeve':['long sleeve']}
        points,analysis,_=self.policy([12,12],query,expected)
        self.assertEqual(points,['b','a']);self.assertEqual(analysis['filters_used'],expected)

    def test_relax_image_only_weakest_first(self):
        query=Mock(side_effect=[[],[],['b']])
        _,analysis,trace=self.policy([60,40,2],query)
        self.assertEqual([r['attribute'] for r in trace['relaxations']],['sleeve','patterns'])
        self.assertEqual(analysis['filters_used'],{'colors':['black']})
        for call in query.call_args_list:self.assertEqual(call.args[1]['colors'],['black'])

    def test_zero_match_never_unfiltered(self):
        query=Mock(return_value=[])
        _,analysis,_=self.policy([0,0],query)
        self.assertEqual(analysis['filters_used'],{'colors':['black']});query.assert_called_once()

    def test_failure_keeps_text(self):
        query=Mock(return_value=['x'])
        self.policy([RuntimeError('secret'),RuntimeError('secret')],query)
        self.assertEqual(query.call_args.args[1],{'colors':['black']})
        with self.assertRaises(RuntimeError):self.policy([0],Mock(side_effect=RuntimeError('offline')))

    def test_encode_once_inherit_without_mutation_or_text_ranking(self):
        search=ProductSearch.__new__(ProductSearch);search.embedder=Mock()
        vector=np.array([1.,0.]);search.embedder.embed_pil_image.return_value=vector
        predictions=attributes(patterns=.1,sleeve=.07);before=deepcopy(predictions)
        search._image_classifier=Mock();search._image_classifier.analyze.return_value=predictions
        search.client=Mock();search.client.count.return_value=SimpleNamespace(count=100)
        search.collection_name='existing'
        search._query_qdrant=Mock(return_value=[SimpleNamespace(id='b',score=.8,payload={'product_id':'b'})])
        result=search.search_by_image_with_overrides(Image.new('RGB',(8,8)),{'colors':['white']},1)
        self.assertEqual(result['resolved_attributes']['colors'],['white'])
        self.assertEqual(result['resolved_attributes']['patterns'],['plain']);self.assertEqual(predictions,before)
        search.embedder.embed_pil_image.assert_called_once();search.embedder.embed_texts.assert_not_called()
        self.assertIs(search._query_qdrant.call_args.kwargs['query_vector'],vector)
        search._image_classifier.analyze.side_effect=RuntimeError('secret')
        result=search.search_by_image_with_overrides(Image.new('RGB',(8,8)),{'buttons':False},1)
        self.assertEqual(result['image_analysis']['filters_used'],{'buttons':False})

class ExtractionTests(unittest.TestCase):
    def extract(self,intent='modify',overrides=None,unsupported=None):
        extractor=QueryAttributeExtractor.__new__(QueryAttributeExtractor);extractor.client=Mock();extractor.model='existing'
        values={key:None if key=='buttons' else [] for key in ATTRIBUTE_LABELS};values.update(overrides or {})
        extractor.client.responses.create.return_value=SimpleNamespace(output_text=json.dumps({'intent':intent,'overrides':values,'unsupported_text':unsupported or []}))
        return extractor.extract_image_overrides('user text'),extractor

    def test_explicit_only_bool_and_shared_model(self):
        result,extractor=self.extract(overrides={'colors':['black'],'buttons':False})
        self.assertEqual(result['overrides'],{'colors':['black'],'buttons':False})
        self.assertEqual(extractor.client.responses.create.call_args.kwargs['model'],'existing')
        call=extractor.client.responses.create.call_args.kwargs
        self.assertEqual(call['input'][0],{'role':'system','content':call['instructions']})
        self.assertEqual(call['input'][1],{'role':'user','content':'user text'})

    def test_invalid_unknown_empty_contradictory_fail_closed(self):
        with self.assertRaises(ValueError):self.extract(overrides={'patterns':['graphic']})
        self.assertEqual(self.extract()[0]['intent'],'clarification')
        self.assertEqual(self.extract(overrides={'sleeve':['short sleeve','long sleeve']})[0]['intent'],'clarification')
        self.assertEqual(self.extract(intent='noop',unsupported=['future'])[0]['intent'],'clarification')

class MixedApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(api.app);self.addCleanup(self.client.close)
        self.extractor=Mock();self.search=Mock()
        self.search.search_by_image_hybrid.return_value={'results':[]}
        self.search.search_by_image_with_overrides.return_value={'results':[],'resolved_attributes':{'colors':['black']}}
        for name,value in [('_get_override_extractor',self.extractor),('_get_image_search',self.search)]:
            p=patch.object(api,name,return_value=value);setattr(self,name,p.start());self.addCleanup(p.stop)
    def post(self,query=''):
        return self.client.post('/api/image-search',files={'image':('x.jpg',image_bytes(),'image/jpeg')},data={'query':query})
    def test_pure_blank_never_extract(self):
        for query in ('','  '):self.assertEqual(self.post(query).status_code,200)
        self._get_override_extractor.assert_not_called();self.assertEqual(self.search.search_by_image_hybrid.call_count,2)
    def test_multiple_partial_zero_match(self):
        for overrides,unsupported in [({'colors':['black']},[]),({'colors':['black'],'sleeve':['short sleeve']},[]),({'colors':['black']},['more futuristic'])]:
            self.extractor.extract_image_overrides.return_value={'intent':'modify','overrides':overrides,'unsupported_text':unsupported}
            body=self.post('make it black').json();self.assertEqual(body['products'],[])
            self.assertIn('No designs matched all',body['text']);self.assertEqual(body['text_analysis']['overrides'],overrides)
            if unsupported:self.assertIn('not applied: more futuristic',body['text'])
            self.assertEqual(self.search.search_by_image_with_overrides.call_args.args[1],overrides)
        self.search.search_by_image_hybrid.assert_not_called()
    def test_guardrail_unsupported_clarification_no_retrieval(self):
        for intent in ('unrelated','unsupported','clarification'):
            self.extractor.extract_image_overrides.return_value={'intent':intent,'overrides':{},'unsupported_text':[]}
            body=self.post('request').json();self.assertEqual(body['search_strategy'],'none');self.assertEqual(body['products'],[])
        self._get_image_search.assert_not_called()
    def test_noop_v2(self):
        self.extractor.extract_image_overrides.return_value={'intent':'noop','overrides':{},'unsupported_text':[]}
        self.assertEqual(self.post('find similar ones').status_code,200)
        self.search.search_by_image_hybrid.assert_called_once();self.search.search_by_image_with_overrides.assert_not_called()
    def test_extraction_failure_length(self):
        self.extractor.extract_image_overrides.side_effect=RuntimeError('credentials')
        response=self.post('black');self.assertEqual(response.status_code,502);self.assertNotIn('credentials',response.text)
        self._get_image_search.assert_not_called();self.assertEqual(self.post('x'*2001).status_code,422)

if __name__=='__main__':unittest.main()
