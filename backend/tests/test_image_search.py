"""Offline image retrieval tests; real PIL/RGB/normalization, mocked inference/Qdrant."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import torch
from PIL import Image

from src.extract_embeding import FashionClipEmbedder
from src.product_search import ProductSearch


def point(identifier, score=0.8):
    return SimpleNamespace(id=f'point-{identifier}', score=score, payload={
        'product_id': identifier, 'image_url': f'data/images/tshirt/{identifier}.jpg',
        'category': 't-shirt', 'colors': ['white'], 'patterns': ['plain'],
        'neckline': 'crew neck', 'sleeve': 'short sleeve',
        'style': ['minimalist'], 'buttons': False,
    })


class ImageSearchTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'query.png'
        Image.new('L', (16, 16), 128).save(self.path)
        self.search = ProductSearch.__new__(ProductSearch)
        embedder = FashionClipEmbedder.__new__(FashionClipEmbedder)
        embedder.device = torch.device('cpu')

        def process(**kwargs):
            self.assertEqual(kwargs['images'].mode, 'RGB')
            self.assertEqual(kwargs['return_tensors'], 'pt')
            return {'pixel_values': torch.zeros(1, 3, 16, 16)}

        embedder.processor = Mock(side_effect=process)
        embedder.model = SimpleNamespace(get_image_features=Mock(
            return_value=torch.tensor([[3., 4., 0.]])))
        self.search.embedder = embedder
        self.search.attribute_extractor = Mock()
        self.search._query_qdrant = Mock(return_value=[point('a', .99), point('b', .91), point('c')])

    def test_valid_jpeg_png_pass_normalized_image_vector_without_filters(self):
        for suffix in ('.jpg', '.png'):
            with self.subTest(suffix=suffix):
                path = self.path.with_suffix(suffix)
                Image.new('L', (16, 16), 128).save(path)
                result = self.search.search_by_image_path(str(path), limit=2)
                kwargs = self.search._query_qdrant.call_args.kwargs
                np.testing.assert_allclose(kwargs['query_vector'], [.6, .8, 0])
                self.assertIsNone(kwargs['query_filter'])
                self.assertEqual(kwargs['limit'], 2)
                self.assertEqual(result['embedding_dimension'], 3)
                self.assertEqual(result['query_image'], str(path))
                self.assertEqual(result['result_count'], 2)
        self.search.attribute_extractor.extract.assert_not_called()

    def test_order_limit_payload_and_no_quality_cutoff(self):
        self.search._query_qdrant.return_value = [point('b', .9), point('a', .2), point('c', .1)]
        result = self.search.search_by_image_path(self.path, limit=2)
        self.assertEqual([p['product_id'] for p in result['results']], ['b', 'a'])
        self.assertEqual(result['results'][1], {
            'point_id': 'point-a', 'product_id': 'a', 'similarity_score': .2,
            'image_path': 'data/images/tshirt/a.jpg', 'attributes': {
                'category': 't-shirt', 'colors': ['white'], 'patterns': ['plain'],
                'neckline': 'crew neck', 'sleeve': 'short sleeve',
                'style': ['minimalist'], 'buttons': False}, 'label_matches': {}})

    def test_missing_directory_and_invalid_image_do_not_query(self):
        for path in (self.path.parent / 'missing.jpg', self.path.parent):
            with self.assertRaisesRegex(FileNotFoundError, 'does not exist or is not a file'):
                self.search.search_by_image_path(path)
        self.path.write_text('not an image')
        with self.assertRaisesRegex(ValueError, 'could not be decoded'):
            self.search.search_by_image_path(self.path)
        self.search._query_qdrant.assert_not_called()
        self.search.embedder.model.get_image_features.assert_not_called()

    def test_invalid_limits_fail_before_embedding(self):
        for limit in (0, 21, True, 1.5, '8'):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.search.search_by_image_path(self.path, limit=limit)
        self.search.embedder.processor.assert_not_called()
        self.search._query_qdrant.assert_not_called()

    def test_empty_results_and_shared_embedder(self):
        embedder = self.search.embedder
        self.search._query_qdrant.return_value = []
        for _ in range(2):
            result = self.search.search_by_image_path(self.path)
            self.assertEqual(result['results'], [])
            self.assertEqual(result['result_count'], 0)
        self.assertIs(self.search.embedder, embedder)
        self.assertEqual(embedder.model.get_image_features.call_count, 2)

    def test_path_and_memory_use_identical_ingestion_pipeline(self):
        with Image.open(self.path) as image:
            ingestion_vector = self.search.embedder.embed_image(self.path)
            memory_vector = self.search.embedder.embed_pil_image(image)
            memory_result = self.search.search_by_image(image, limit=2)
            self.assertEqual(image.size, (16, 16))  # Caller retains ownership.
        np.testing.assert_array_equal(ingestion_vector, memory_vector)
        path_result = self.search.search_by_image_path(self.path, limit=2)
        self.assertEqual(path_result['results'], memory_result['results'])
        self.assertEqual(path_result['embedding_dimension'], memory_result['embedding_dimension'])

    def test_text_search_keeps_prefix_filters_and_result_shape(self):
        self.search.embedder.embed_texts = Mock(return_value=np.array([[.6, .8, 0]]))
        result = self.search.search('white tee', filters={'colors': ['white']}, limit=2, allow_fallback=False)
        self.search.embedder.embed_texts.assert_called_once_with(['a product photo of a t-shirt matching: white tee'])
        self.assertEqual(result['query'], 'white tee')
        self.assertEqual(result['extracted_attributes'], {'colors': ['white']})
        self.assertEqual([p['product_id'] for p in result['results']], ['a', 'b'])
        self.assertEqual(result['results'][0]['label_matches'], {'colors': True})
        self.search._query_qdrant.assert_called_once()
        self.assertIsNotNone(self.search._query_qdrant.call_args.kwargs['query_filter'])
        self.search.embedder.model.get_image_features.assert_not_called()

    def test_text_fallback_keeps_order_and_point_deduplication(self):
        self.search.embedder.embed_texts = Mock(return_value=np.array([[1., 0, 0]]))
        self.search._query_qdrant.side_effect = [[point('a')], [point('a'), point('b'), point('c')]]
        result = self.search.search('white tee', filters={'colors': ['white']}, limit=2)
        self.assertEqual([p['product_id'] for p in result['results']], ['a', 'b'])
        self.assertEqual(self.search._query_qdrant.call_args.kwargs['limit'], 6)
        self.assertIsNone(self.search._query_qdrant.call_args.kwargs['query_filter'])


if __name__ == '__main__':
    unittest.main()
