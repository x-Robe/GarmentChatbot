"""Deterministic resolver-output contracts, not claims of live language accuracy."""
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import api
from src.result_count import ResultCount, DEFAULT_RESULT_COUNT, MAX_RESULT_COUNT
from src.query_attribute_extractor import QueryAttributeExtractor
from src.zero_shot_classifier import ATTRIBUTE_LABELS
import test_chatbot_results as fixtures
from test_image_context import reference, active
import test_image_context as image_fixtures
from test_image_api import image_bytes

class CountTests(unittest.TestCase):
    def agent(self, **kwargs):
        return fixtures.AgentTests().agent(**kwargs)[0]

    def test_schema_single_resolver(self):
        a=self.agent(); schema=a.tools[0]['parameters']
        self.assertEqual(schema['properties']['result_count']['type'],['integer','null'])
        self.assertIn('result_count',schema['required']);self.assertEqual(len(a.tools),1)

    def test_defaults_caps_and_malformed(self):
        self.assertEqual(ResultCount().effective,8)
        for value in (9,12,1000000):
            c=ResultCount(value);self.assertEqual(c.effective,MAX_RESULT_COUNT);self.assertTrue(c.metadata()['count_capped'])
        for value in (True,False,'3',3.0,[],{}):
            with self.assertRaises(ValueError):ResultCount(value)

    def test_language_contract_and_clean_query(self):
        for query,count,clean in [('Show me 7 black T-shirts',7,'black T-shirts'),('Give me two designs',2,'T-shirts'),
                ('找七件黑色T恤',7,'黑色T恤'),('给我三张图片',3,'T-shirts'),('給我三張圖片',3,'T-shirts'),
                ('有冇兩件其他款',2,'T-shirts')]:
            with self.subTest(query=query):
                a=self.agent(count=count,resolved=clean,relation='new_topic',similar=[fixtures.product(i) for i in range(10)])
                r=a.respond(query);self.assertEqual(r['requested_count'],count);self.assertEqual(len(r['products']),count)
                self.assertEqual(r['resolved_query'],clean)
                self.assertEqual(a._execute_tool.call_args_list[0].args[1]['query'],clean)
                self.assertEqual(a.client.responses.create.call_count,2)

    def test_noncount_numbers_and_vague_default(self):
        for query in ('size 10 T-shirts','2025 fashion trends','shirt with 7 printed on it','3/4 sleeve shirts',
                      'shirts under $20','some shirts','a few shirts'):
            a=self.agent(relation='new_topic',similar=[fixtures.product(i) for i in range(10)])
            r=a.respond(query);self.assertEqual(r['effective_count'],8);self.assertIsNone(r['requested_count'])
            self.assertEqual(r['resolved_query'],query)

    def test_modes_counts_and_exact_precedence(self):
        for mode in ('auto','exact','similar','default'):
            for route in ('exact','similar','both'):
                for count in range(1,9):
                    a=self.agent(strategy=route,count=count,exact=[fixtures.product(i) for i in range(8)],
                                 similar=[fixtures.product(i) for i in range(4,12)])
                    r=a.respond('counted shirts',mode);p=r['products']
                    self.assertEqual(len(p),count);self.assertEqual(len({v['product_id'] for v in p}),count)
                    if r['search_strategy']!='similar':self.assertEqual(p[0]['match_type'],'exact')
                    self.assertEqual(len(r['active_search']['shown_product_ids']),count)
                    self.assertNotIn('result_count',r['active_search'])
                    for call in a._execute_tool.call_args_list[1:]:self.assertEqual(call.args[1]['limit'],count)

    def test_pagination_count_not_sticky_and_only_displayed_tracked(self):
        state=None;seen=set()
        for count in (7,3,5,None):
            a=self.agent(strategy='exact',count=count,resolved='black shirts',relation='new_topic' if state is None else 'more_results')
            def execute(name,args):
                if name=='extract_query_attributes':return {'colors':['black']}
                self.assertEqual(set(args.get('excluded',{}).get('shown_product_ids',[])),seen)
                return {'results':[fixtures.product(str(i)) for i in range(100) if str(i) not in seen][:args['limit']]}
            a._execute_tool=Mock(side_effect=execute)
            r=a.respond('more' if state else 'show seven black shirts',active_search=state)
            ids={p['product_id'] for p in r['products']};self.assertFalse(seen&ids)
            self.assertEqual(len(ids),count or 8);seen|=ids;state=r['active_search']
            self.assertEqual(set(state['shown_product_ids']),seen)
            self.assertEqual(state['resolved_query'],'black shirts')

    def test_refinement_and_new_topic_reset(self):
        first=self.agent(count=3,similar=[fixtures.product(i) for i in range(8)]).respond('3 shirts')
        for relation in ('refinement','new_topic'):
            r=self.agent(relation=relation,resolved='white shirts',similar=[fixtures.product(i) for i in range(8)]).respond('white shirts',active_search=first['active_search'])
            self.assertEqual(r['effective_count'],8);self.assertEqual(len(r['products']),8)

    def test_invalid_never_searches(self):
        for count in (0,-5):
            a=self.agent(count=count);r=a.respond('invalid quantity')
            self.assertEqual(r['intent'],'clarification');self.assertIsNone(r['effective_count'])
            self.assertEqual(r['products'],[]);a._execute_tool.assert_not_called()
            self.assertEqual(a.client.responses.create.call_count,1)
        for count in ('3',3.5,True):
            a=self.agent(count=count)
            with self.assertRaises(ValueError):a.respond('bad count')
            a._execute_tool.assert_not_called()

    def test_cap_and_fewer_or_empty_no_quota_filling(self):
        for n in (0,2,8):
            a=self.agent(strategy='exact',count=12,exact=[fixtures.product(i) for i in range(n)])
            r=a.respond('12 shirts');self.assertEqual(len(r['products']),n)
            self.assertTrue(r['count_capped']);self.assertIn('up to 8',r['text']);self.assertIsNone(r['has_more'])

    def test_counted_exhaustion_keeps_state_and_never_fabricates(self):
        first=self.agent(strategy='exact',count=3,exact=[fixtures.product('1')]).respond('3 black shirts')
        state=deepcopy(first['active_search'])
        r=self.agent(strategy='exact',count=5,relation='more_results').respond('5 more',active_search=state)
        self.assertEqual(r['products'],[]);self.assertFalse(r['has_more'])
        self.assertEqual(r['active_search'],state);self.assertEqual(r['effective_count'],5)

    def test_quantity_and_visual_number_are_separate(self):
        a=self.agent(count=2,resolved='shirts with number 7 printed on them',relation='new_topic')
        r=a.respond('Show two shirts with number 7 printed on them')
        self.assertEqual(r['effective_count'],2);self.assertIn('7',r['resolved_query'])
        self.assertNotIn('two',r['resolved_query'])

    def test_existing_relative_tail_and_order(self):
        candidates=[fixtures.product('a',.9),fixtures.product('b',.8),fixtures.product('c',.7)]
        r=self.agent(count=7,similar=candidates).respond('7 shirts')
        self.assertEqual([p['product_id'] for p in r['products']],['a','b'])
        self.assertEqual(candidates[0]['similarity_score'],.9)

    def test_image_continuation_count_and_frozen_vector(self):
        a=image_fixtures.ContinuationTests().agent('image_more_results')
        # Replace only mocked resolver output; retain existing image fixtures.
        a.client.responses.create.side_effect=None
        a.client.responses.create.return_value=NS(id='plan',output=[NS(type='function_call',name='plan_request',call_id='p',arguments=json.dumps({
            'intent':'search','search_strategy':'none','relation_to_context':'image_more_results','resolved_query':'same image','result_count':3}))])
        before=active(colors=['black']);r=a.respond('show 3 more',active_search=before,reference_image=reference())
        kwargs=a.product_search.search_by_image_embedding.call_args.kwargs
        self.assertEqual(kwargs['limit'],3);self.assertEqual(kwargs['effective_filters'],before['effective_filters'])
        self.assertEqual(kwargs['excluded']['shown_product_ids'],before['shown_product_ids'])
        self.assertEqual(r['effective_count'],3);a.attribute_extractor.extract_image_overrides.assert_not_called()

class ImageCountTests(unittest.TestCase):
    def test_same_extractor_schema_and_language_contract(self):
        for query,count in [('show 5 similar black shirts',5),('找五件黑色上衣',5),('再給我三件',3),('some shirts',None)]:
            e=QueryAttributeExtractor.__new__(QueryAttributeExtractor);e.model='existing';e.client=Mock()
            values={k:None if k=='buttons' else [] for k in ATTRIBUTE_LABELS};values['colors']=['black']
            e.client.responses.create.return_value=NS(output_text=json.dumps({'intent':'modify','overrides':values,'unsupported_text':[],'result_count':count}))
            r=e.extract_image_overrides(query);self.assertEqual(r['result_count'],count);e.client.responses.create.assert_called_once()
            self.assertIn('result_count',e.client.responses.create.call_args.kwargs['text']['format']['schema']['required'])

    def test_upload_count_precedence_validation_and_legacy_limit(self):
        with TestClient(api.app) as c,patch.object(api,'_get_override_extractor') as extract,patch.object(api,'_get_image_search') as get:
            search=get.return_value;search.search_by_image_with_overrides.return_value={'results':[fixtures.product(i) for i in range(10)]}
            search.search_by_image_hybrid.return_value={'results':[fixtures.product(i) for i in range(10)]}
            for count,expected in ((5,5),(None,2),(12,8),(0,0),(-5,0)):
                extract.return_value.extract_image_overrides.return_value={'intent':'modify','overrides':{'colors':['black']},'unsupported_text':[],'result_count':count}
                get.reset_mock();response=c.post('/api/image-search',files={'image':('a.jpg',image_bytes(),'image/jpeg')},data={'query':'black shirts','limit':2})
                self.assertEqual(response.status_code,200);r=response.json();self.assertEqual(len(r['products']),expected)
                if expected:self.assertEqual(search.search_by_image_with_overrides.call_args.kwargs['limit'],expected)
                else:get.assert_not_called();self.assertEqual(r['intent'],'clarification')
            r=c.post('/api/image-search',files={'image':('a.jpg',image_bytes(),'image/jpeg')},data={'limit':3}).json()
            self.assertEqual(len(r['products']),3)
            self.assertEqual(r['effective_count'],3)

    def test_unsupported_image_keeps_requested_count_without_execution_budget(self):
        with TestClient(api.app) as c,patch.object(api,'_get_override_extractor') as extract,patch.object(api,'_get_image_search') as search:
            extract.return_value.extract_image_overrides.return_value={'intent':'unsupported','overrides':{},'unsupported_text':['futuristic'],'result_count':5}
            r=c.post('/api/image-search',files={'image':('a.jpg',image_bytes(),'image/jpeg')},data={'query':'5 futuristic shirts'}).json()
        self.assertEqual(r['requested_count'],5);self.assertIsNone(r['effective_count'])
        self.assertEqual(r['products'],[]);search.assert_not_called()

    def test_chat_api_preserves_count_metadata(self):
        a=fixtures.AgentTests().agent(count=7,similar=[fixtures.product(i) for i in range(10)])[0]
        with TestClient(api.app) as c,patch.object(api,'_agent',a):
            r=c.post('/api/chat',json={'query':'7 shirts'}).json()
        self.assertEqual(r['requested_count'],7);self.assertEqual(r['effective_count'],7)
        self.assertEqual(len(r['products']),7);self.assertFalse(r['count_capped'])
