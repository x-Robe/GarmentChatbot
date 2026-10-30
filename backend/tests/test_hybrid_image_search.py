"""Offline policy and pipeline tests; no model downloads, Qdrant or LLM."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image
from src.zero_shot_classifier import ATTRIBUTE_LABELS, PROMPT_TEMPLATES, ZeroShotTshirtClassifier
from src.hybrid_image_search import retrieve_hybrid
from src.product_search import ProductSearch


def attributes(**margins):
    return {key: {'label': labels[0], 'score': .4, 'runner_up': labels[1],
                  'runner_up_score': .4-margins.get(key, .001), 'margin': margins.get(key,.001)}
            for key, labels in ATTRIBUTE_LABELS.items()}


class ClassifierTests(unittest.TestCase):
    def test_same_prompts_top_runner_and_margin_all_categories(self):
        def embeddings(prompts):
            # Unit vectors with known cosine to [1,0].
            scores = np.linspace(.8,.1,len(prompts))
            return np.array([[score,np.sqrt(1-score**2)] for score in scores])
        embed = Mock(side_effect=embeddings)
        classifier = ZeroShotTshirtClassifier(embed)
        report = classifier.analyze(np.array([2.,0.]))
        self.assertEqual(set(report),set(ATTRIBUTE_LABELS))
        for (key, labels), call in zip(ATTRIBUTE_LABELS.items(),embed.call_args_list):
            self.assertEqual(call.args[0],[PROMPT_TEMPLATES[key].format(label=l) for l in labels])
            self.assertEqual(report[key]['label'],labels[0])
            self.assertEqual(report[key]['runner_up'],labels[1])
            self.assertAlmostEqual(report[key]['score'],.8)
            self.assertAlmostEqual(report[key]['margin'],.7/(len(labels)-1))
        # analyze is additive: ingestion classification still uses original methods.
        self.assertEqual(classifier.classify(np.array([1.,0.]))['buttons'],True)


class PolicyTests(unittest.TestCase):
    def run_policy(self, predictions=None, counts=None, query=None):
        predictions = predictions or attributes(colors=.08, sleeve=.06, patterns=.04, style=.02)
        count = Mock(side_effect=counts) if counts is not None else Mock(return_value=100)
        query = query or Mock(return_value=['first','second'])
        result = retrieve_hybrid(np.array([1.,0.]),predictions,2,count,query,ProductSearch._build_filter)
        return result,count,query

    def test_strongest_two_filters_schema_values_order_and_no_manual_ranking(self):
        (points,analysis,trace),count,query=self.run_policy()
        self.assertEqual(points,['first','second'])
        self.assertEqual(analysis['filters_used'],{'colors':'black','sleeve':'sleeveless'})
        self.assertFalse(analysis['attributes']['style']['used_for_filter'])
        self.assertEqual(trace['target_candidates'],8)
        actual=query.call_args.args[1].must
        self.assertEqual([(f.key,f.match.any) for f in actual],[('colors',['black']),('sleeve',['sleeveless'])])
        self.assertEqual(count.call_count,2)

    def test_bool_normalization_matches_ingestion(self):
        predictions=attributes(buttons=.09)
        predictions['buttons'].update(label='without visible buttons',runner_up='with visible buttons')
        (_,analysis,_),_,query=self.run_policy(predictions)
        self.assertIs(analysis['filters_used']['buttons'],False)
        self.assertIs(query.call_args.args[1].must[0].match.value,False)

    def test_pool_protection_keeps_previous_filter_and_stops(self):
        (_,analysis,trace),count,_=self.run_policy(counts=[50,7])
        self.assertEqual(analysis['filters_used'],{'colors':'black'})
        self.assertEqual(trace['attempts'][-1]['decision'],'pool_too_small')
        self.assertEqual(analysis['candidate_count'],50)
        self.assertEqual(count.call_count,2)

    def test_weak_unknown_and_ambiguous_style_do_not_filter(self):
        predictions=attributes(style=.03)
        predictions['colors'].update(label='invented',margin=.9)
        (_,analysis,_),_,query=self.run_policy(predictions)
        self.assertEqual(analysis['filters_used'],{})
        self.assertEqual(analysis['strategy'],'pure_visual')
        self.assertIsNone(query.call_args.args[1])

    def test_no_viable_filter_falls_back_to_original_query_vector(self):
        (_,analysis,trace),_,query=self.run_policy(counts=[0,5])
        self.assertEqual(analysis['strategy'],'pure_visual')
        np.testing.assert_array_equal(query.call_args.args[0],[1.,0.])
        self.assertEqual(trace['candidate_availability'],5)
        self.assertIsNone(query.call_args.args[1])

    def test_weakest_relaxed_when_query_underfills_despite_count(self):
        query=Mock(side_effect=[['one'],['first','second']])
        (_,analysis,trace),_,_=self.run_policy(query=query)
        self.assertEqual(analysis['filters_used'],{'colors':'black'})
        self.assertEqual(trace['relaxations'][0]['attribute'],'sleeve')
        self.assertEqual(query.call_count,2)

    def test_all_filters_relaxed_to_baseline(self):
        query=Mock(side_effect=[[],[],['first','second']])
        (_,analysis,trace),_,_=self.run_policy(query=query)
        self.assertEqual([r['attribute'] for r in trace['relaxations']],['sleeve','colors'])
        self.assertEqual(analysis['strategy'],'pure_visual')
        self.assertIsNone(query.call_args.args[1])

    def test_count_or_filtered_query_error_does_not_break_baseline(self):
        (_,analysis,_),_,query=self.run_policy(counts=[RuntimeError('secret'),100])
        self.assertEqual(analysis['strategy'],'pure_visual')
        self.assertIsNone(query.call_args.args[1])
        query=Mock(side_effect=[RuntimeError('secret'),['first','second']])
        (_,analysis,trace),_,_=self.run_policy(query=query)
        self.assertEqual(analysis['filters_used'],{'colors':'black'})
        self.assertNotIn('secret',str(trace))


class HybridPipelineTests(unittest.TestCase):
    def setUp(self):
        self.search=ProductSearch.__new__(ProductSearch)
        self.search.embedder=Mock()
        self.vector=np.array([1.,0.])
        self.search.embedder.embed_pil_image.return_value=self.vector
        self.search.client=Mock()
        self.search.client.count.return_value=SimpleNamespace(count=100)
        self.search.collection_name='existing'
        self.search._query_qdrant=Mock(return_value=[SimpleNamespace(id='b',score=.7,payload={'product_id':'b'}),SimpleNamespace(id='a',score=.2,payload={'product_id':'a'})])

    def test_single_encoding_classifier_reuse_order_and_safe_diagnostics(self):
        classifier=Mock()
        classifier.analyze.return_value=attributes(colors=.08)
        with patch('src.product_search.ZeroShotTshirtClassifier',return_value=classifier) as factory:
            image=Image.new('RGB',(8,8))
            for _ in range(2):
                result=self.search.search_by_image_hybrid(image,limit=2)
                self.assertNotIn('diagnostics',result)
                self.assertEqual([p['product_id'] for p in result['results']],['b','a'])
            self.assertEqual(self.search.embedder.embed_pil_image.call_count,2)
            factory.assert_called_once_with(self.search.embedder.embed_texts)
            self.assertIs(classifier.analyze.call_args.args[0],self.vector)
            self.assertIs(self.search._query_qdrant.call_args.kwargs['query_vector'],self.vector)
            self.assertEqual(self.search.client.count.call_args.kwargs['collection_name'],'existing')
            self.assertTrue(self.search.client.count.call_args.kwargs['exact'])

    def test_classifier_failure_falls_back_without_exposing_error(self):
        with patch('src.product_search.ZeroShotTshirtClassifier',side_effect=RuntimeError('secret')):
            result=self.search.search_by_image_hybrid(Image.new('RGB',(8,8)))
        self.assertEqual(result['image_analysis']['strategy'],'pure_visual')
        self.assertNotIn('secret',str(result))
        self.assertIsNone(self.search._query_qdrant.call_args.kwargs['query_filter'])

    def test_hybrid_limit_capped_before_encoding(self):
        for limit in (0,9,True,1.5):
            with self.assertRaises(ValueError):
                self.search.search_by_image_hybrid(Image.new('RGB',(8,8)),limit=limit)
        self.search.embedder.embed_pil_image.assert_not_called()

if __name__ == '__main__':
    unittest.main()
