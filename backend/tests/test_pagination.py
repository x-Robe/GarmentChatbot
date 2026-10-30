"""Offline state, resolver dispatch, transport, exclusion and history boundaries."""
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models
from src.product_search import ProductSearch
from src.search_state import ActiveSearch, add_displayed
from src.conversation_context import normalize_context, MAX_CONTEXT_CHARS, MAX_CONTEXT_MESSAGES
import test_chatbot_results as fixtures
from test_chatbot_results import product
import api


def state(mode='auto', strategy='both', ids=None):
    return ActiveSearch(search_type='text', resolved_query='black oversized t-shirts',
        mode=mode, search_strategy=strategy, attributes={'colors':['black'],'style':['oversized']},
        shown_product_ids=ids or []).model_dump()

class PaginationTests(unittest.TestCase):
    def agent(self, **kwargs):return fixtures.AgentTests().agent(**kwargs)

    def test_repeated_pages_reuse_query_attributes_mode_and_all_ids(self):
        current=state(ids=['1'])
        for index in (2,3,4):
            a,_=self.agent(strategy='exact',relation='more_results',resolved='WRONG',exact=[product(str(index))],similar=[product('s'+str(index))])
            old=deepcopy(current)
            result=a.respond('show more','similar',active_search=current)
            self.assertEqual(result['resolved_query'],current['resolved_query']);self.assertEqual(result['search_strategy'],'both')
            self.assertEqual(a._execute_tool.call_count,2)
            for call in a._execute_tool.call_args_list:
                self.assertEqual(call.args[1]['excluded']['shown_product_ids'],current['shown_product_ids'])
                self.assertEqual(call.args[1]['attributes']['colors'],['black'])
            self.assertEqual(current,old)
            current=result['active_search']
        self.assertEqual(current['shown_product_ids'],['1','2','s2','3','s3','4','s4'])

    def test_new_and_refinement_reset_exclusions_allow_reappearing_product(self):
        for relation in ('new_topic','refinement','continuation'):
            a,_=self.agent(strategy='exact',relation=relation,resolved='white tee',exact=[product('1')])
            result=a.respond('white tee',active_search=state(ids=['1','2']))
            self.assertEqual(result['active_search']['shown_product_ids'],['1'])
            self.assertEqual(result['resolved_query'],'white tee')
            self.assertEqual(a._execute_tool.call_args_list[0].args[0],'extract_query_attributes')
            self.assertTrue(all('excluded' not in c.args[1] for c in a._execute_tool.call_args_list))

    def test_pagination_does_not_need_model_to_reselect_a_route(self):
        a,_=self.agent(strategy='none',relation='more_results',exact=[product('next')])
        result=a.respond('more',active_search=state('exact','exact',['old']))
        self.assertEqual(result['search_strategy'],'exact')
        a,_=self.agent(strategy='none',relation='more_results')
        self.assertEqual(a.respond('more')['intent'],'clarification')

    def test_new_topic_does_not_accept_stale_planner_rewrite(self):
        a,_=self.agent(strategy='exact',relation='new_topic',resolved='stale black oversized',exact=[product('new')])
        result=a.respond('white minimalist tees',active_search=state(ids=['old']))
        self.assertEqual(result['resolved_query'],'white minimalist tees')
        self.assertEqual(result['active_search']['shown_product_ids'],['new'])

    def test_manual_modes_preserved_and_no_ids_in_llm_input(self):
        for mode in ('exact','similar'):
            a,_=self.agent(relation='more_results',strategy='both',exact=[product('new')],similar=[product('new')])
            result=a.respond('有冇其他款？','auto',active_search=state(mode,mode,['secret-id']))
            self.assertEqual(result['search_strategy'],mode)
            self.assertEqual({p['match_type'] for p in result['products']},{mode})
            request=a.client.responses.create.call_args_list[0].kwargs
            self.assertNotIn('secret-id',request['input'][1]['content'])
            self.assertNotIn('shown_product_ids',request['input'][1]['content'])

    def test_only_selected_candidates_tracked_exact_wins(self):
        a,_=self.agent(strategy='both',relation='new_topic',exact=[product(str(i)) for i in range(8)],similar=[product('0'),product('s1'),product('s2'),product('s3')])
        result=a.respond('black tees')
        self.assertEqual(result['active_search']['shown_product_ids'],['0','1','2','3','4','5','s1','s2'])
        self.assertIsNone(result['has_more'])

    def test_partial_final_page_then_zero_and_error_is_not_exhaustion(self):
        active=state('exact','exact',['1'])
        a,_=self.agent(strategy='exact',relation='more_results',exact=[product('2'),product('3'),product('4')])
        r=a.respond('more',active_search=active);self.assertEqual(len(r['products']),3);self.assertIsNone(r['has_more'])
        a,_=self.agent(strategy='exact',relation='more_results')
        r=a.respond('more',active_search=r['active_search']);self.assertEqual(r['products'],[]);self.assertFalse(r['has_more']);self.assertIn("seen all",r['text'])
        a,outputs=self.agent(strategy='both',relation='more_results',similar=[product('new')]);outputs['exact_match_products']=RuntimeError('secret')
        before=deepcopy(active)
        with self.assertRaises(RuntimeError):a.respond('more',active_search=active)
        self.assertEqual(before,active)

    def test_missing_state_and_image_pagination_never_retrieve(self):
        for active in (None,{'search_type':'image'}):
            for relation in ('more_results','refinement') if active else ('more_results',):
                a,_=self.agent(relation=relation)
                result=a.respond('more',active_search=active)
                a._execute_tool.assert_not_called();self.assertEqual(result['intent'],'clarification')
                self.assertIn('reference image' if active else 'What kind',result['text'])

    def test_information_and_domain_leave_active_unchanged(self):
        for intent,relation in [('informational','fashion_information'),('unrelated','out_of_domain')]:
            a,_=self.agent(intent=intent,relation=relation)
            active=state(ids=['1']);r=a.respond('question',active_search=active)
            self.assertEqual(r['active_search'],active);a._execute_tool.assert_not_called()

    def test_id_normalization_fallback_and_state_safety(self):
        s=state(ids=[101,'101']);self.assertEqual(s['shown_product_ids'],['101'])
        point='00000000-0000-0000-0000-000000000001'
        r=add_displayed(ActiveSearch.model_validate(s),[{'point_id':point},{'product_id':102,'point_id':point}])
        self.assertEqual(r['shown_point_ids'],[point]);self.assertEqual(r['shown_product_ids'],['101','102'])
        for invalid in ({**s,'collection':'other'}, {**s,'attributes':{'arbitrary':'value'}},{**s,'shown_product_ids':['x']*4097},{**s,'shown_point_ids':['invalid']}):
            with self.assertRaises(ValueError):ActiveSearch.model_validate(invalid)

    def test_full_context_and_deterministic_boundaries(self):
        history=[{'role':'user' if i%2==0 else 'assistant','text':f'topic {i}'} for i in range(20)]
        self.assertEqual(normalize_context(history),history)
        big=[{'role':'user','text':str(i)+'x'*9990} for i in range(300)]
        result=normalize_context(big)
        self.assertLessEqual(len(result),MAX_CONTEXT_MESSAGES);self.assertLessEqual(sum(len(r['text']) for r in result),MAX_CONTEXT_CHARS)
        self.assertEqual(result[-1],big[-1])
        self.assertEqual(normalize_context([{'role':'user','text':'hello\nvector: [1,2]\napi_key: hidden'}]),[{'role':'user','text':'hello'}])

class QdrantExclusionTests(unittest.TestCase):
    def test_filter_preserves_positive_and_excludes_all_points_of_product(self):
        client=QdrantClient(':memory:');self.addCleanup(client.close)
        client.create_collection('test',vectors_config=models.VectorParams(size=2,distance=models.Distance.COSINE))
        client.upsert('test',points=[models.PointStruct(id=i,vector=[1.,i*.01],payload={'product_id':pid,'colors':[color]}) for i,pid,color in [(1,101,'black'),(2,101,'black'),(3,'101','black'),(4,102,'black'),(5,103,'white'),(6,None,'black')]])
        positive=ProductSearch._build_filter({'colors':['black']});before=positive.model_dump()
        f=ProductSearch._exclude_shown(positive,{'shown_product_ids':['101'],'shown_point_ids':['6']})
        found=client.query_points('test',query=[1.,0.],query_filter=f,limit=8).points
        self.assertEqual([p.id for p in found],[4]);self.assertEqual(positive.model_dump(),before)

    def test_adaptive_index_fallback_excludes_duplicate_product_points_and_is_bounded(self):
        search=ProductSearch.__new__(ProductSearch)
        class IndexErrorResponse(Exception):
            status_code=400
            content=b'Index required for product_id integer'
        old=[NS(id=i,payload={"product_id":101}) for i in range(5)]
        new=NS(id=9,payload={"product_id":102})
        search._query_qdrant=Mock(side_effect=[IndexErrorResponse(),old[:2],old[:4],old+[new]])
        positive=ProductSearch._build_filter({"colors":["black"]})
        result=search._query_text_page([1,0],positive,2,{"shown_product_ids":["101"],"shown_point_ids":["1"]})
        self.assertEqual(result,[new])
        self.assertEqual([c.kwargs["limit"] for c in search._query_qdrant.call_args_list],[2,2,4,8])
        for c in search._query_qdrant.call_args_list:
            self.assertEqual(c.kwargs["query_filter"].must,positive.must)
        search._query_qdrant=Mock(side_effect=lambda **kw:[old[0]]*kw['limit'])
        with self.assertRaisesRegex(RuntimeError,'budget'):
            search._query_text_page([1,0],positive,8,{"shown_product_ids":["101"]})
        self.assertEqual(search._query_qdrant.call_args.kwargs['limit'],4096)

    def test_query_receives_exclusion_before_retrieval(self):
        search=ProductSearch.__new__(ProductSearch);search.embedder=Mock()
        import numpy as np
        search.embedder.embed_texts.return_value=np.array([[1.,0.]])
        search._query_qdrant=Mock(return_value=[])
        search.search('black',filters={'colors':['black']},excluded={'shown_product_ids':['101']},allow_fallback=False)
        f=search._query_qdrant.call_args.kwargs['query_filter']
        self.assertTrue(f.must);self.assertEqual(len(f.must_not),2)

class StateApiTests(unittest.TestCase):
    def test_optional_state_validation_and_old_request(self):
        with TestClient(api.app) as client,patch.object(api,'_agent',Mock()) as agent:
            agent.respond.return_value={'text':'ok','response_id':'x','products':[],'search_results':{'exact':[],'similar':[]}}
            self.assertEqual(client.post('/api/chat',json={'query':'tee'}).status_code,200)
            response=client.post('/api/chat',json={'query':'more','active_search':state(ids=[101])})
            self.assertEqual(response.status_code,200)
            self.assertEqual(agent.respond.call_args.kwargs['active_search']['shown_product_ids'],['101'])
            for bad in ({'search_type':'text'}, {**state(),'attributes':{'secret':'bad'}}, {**state(),'shown_product_ids':['1']*4097}):
                response=client.post('/api/chat',json={'query':'more','active_search':bad})
                self.assertEqual(response.status_code,422);self.assertNotIn('secret',response.text)

if __name__=='__main__':unittest.main()
