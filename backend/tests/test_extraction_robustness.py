import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
import openai
import httpx
from src.query_attribute_extractor import QueryAttributeExtractor, DEFAULT_SCHEMA_PATH

class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.ex = QueryAttributeExtractor.__new__(QueryAttributeExtractor)
        self.ex.schema = json.loads(DEFAULT_SCHEMA_PATH.read_text())
        self.ex.output_schema = self.ex._build_strict_schema()
        self.ex.model = 'test'
        self.create = Mock()
        self.ex.client = SimpleNamespace(responses=SimpleNamespace(create=self.create))

    def test_provider_schema_omits_unsupported_unique_items(self):
        self.assertNotIn('uniqueItems', json.dumps(self.ex.output_schema))

    def test_known_attributes_survive_and_unknown_concepts_stay_semantic(self):
        cases = [
            ('Korean style t-shirt', {'style':['Korean']}, []),
            ('Japanese style t-shirt', {'style':['Japanese']}, []),
            ('Japanese streetwear graphic T-shirts', {'style':['streetwear'], 'patterns':['graphic']}, ['streetwear']),
            ('white minimalist t-shirt', {'colors':['white'], 'style':['minimalist']}, ['minimalist']),
            ('cyberpunk oversized black t-shirt', {'colors':['black'], 'style':['cyberpunk','oversized']}, ['oversized']),
            ('Y2K quiet luxury Tokyo streetwear', {'style':['Y2K','quiet luxury','streetwear']}, ['streetwear']),
        ]
        for query, fields, styles in cases:
            with self.subTest(query=query):
                self.create.return_value = SimpleNamespace(output_text=json.dumps({**fields,'search_text':'lost original concept'}))
                result = self.ex.extract(query)
                self.assertEqual(result['search_text'], query)
                self.assertEqual(result['style'], styles)
                for field in ('colors','patterns'):
                    self.assertEqual(result[field], fields.get(field,[]))

    def test_malformed_missing_and_null_fields_have_safe_defaults(self):
        for raw in ('not JSON','[]','null','{}','{"style":null,"colors":["black","black","invented"],"buttons":"yes"}'):
            self.create.return_value = SimpleNamespace(output_text=raw)
            result=self.ex.extract('cyberpunk tee')
            self.assertEqual(result['search_text'],'cyberpunk tee')
            self.assertIsNone(result['buttons'])
            self.assertEqual(result['style'],[])
            self.assertEqual(result['colors'],['black'] if 'black' in raw else [])

    def test_fenced_json_retains_valid_attributes(self):
        self.create.return_value=SimpleNamespace(output_text='```json\n{"colors":["white"]}\n```')
        self.assertEqual(self.ex.extract('white tee')['colors'],['white'])

    def test_provider_failure_keeps_original_query_without_fabricating_filters(self):
        self.create.side_effect=openai.BadRequestError('unsupported schema',response=httpx.Response(400,request=httpx.Request('POST','https://example.invalid')),body=None)
        result=self.ex.extract('Korean tee')
        self.assertEqual(result['search_text'],'Korean tee')
        self.assertTrue(all(v in (None,[]) for k,v in result.items() if k!='search_text'))
