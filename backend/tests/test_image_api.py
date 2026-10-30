"""Multipart transport tests: real image decoding, mocked retrieval, no paid calls."""
import asyncio
from copy import deepcopy
from io import BytesIO
from unittest import TestCase, main
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image, features

import api
from src.image_upload import ImageUploadSizeLimit, MAX_IMAGE_BYTES, MAX_MULTIPART_BYTES


def image_bytes(fmt='JPEG'):
    output = BytesIO()
    Image.new('RGB', (16, 16), 'navy').save(output, format=fmt)
    return output.getvalue()


class ImageApiTests(TestCase):
    def setUp(self):
        self.search = Mock()
        self.raw = {'results': [
            {'product_id': str(i), 'point_id': f'point-{i}', 'similarity_score': score,
             'image_path': f'data/images/tshirt/{i}.jpg', 'attributes': {'colors': ['blue']},
             'label_matches': {}}
            for i, score in ((2, .9), (1, .1))]}
        self.search.search_by_image_hybrid.return_value = self.raw
        patcher = patch.object(api, '_get_image_search', return_value=self.search)
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        agent = patch.object(api, '_create_agent', side_effect=AssertionError('No LLM agent'))
        agent.start()
        self.addCleanup(agent.stop)
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)

    def upload(self, payload=None, content_type='image/jpeg', **kwargs):
        return self.client.post('/api/image-search', files={
            'image': ('untrusted.jpg', image_bytes() if payload is None else payload, content_type)}, **kwargs)

    def test_valid_formats_rgb_default_limit_order_urls_no_mutation(self):
        original = deepcopy(self.raw)
        formats = [('JPEG', 'image/jpeg'), ('PNG', 'image/png')]
        if features.check('webp'):
            formats.append(('WEBP', 'image/webp'))
        for fmt, mime in formats:
            with self.subTest(fmt=fmt):
                def search(image, limit):
                    self.assertEqual(image.mode, 'RGB')
                    self.assertEqual(image.size, (16, 16))
                    self.assertEqual(limit, 8)
                    return self.raw
                self.search.search_by_image_hybrid.side_effect = search
                response = self.upload(image_bytes(fmt), mime)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body['search_type'], 'image')
                self.assertEqual([p['product_id'] for p in body['products']], ['2', '1'])
                self.assertEqual(body['products'][1]['similarity_score'], .1)
                for p in body['products']:
                    self.assertEqual(p['match_type'], 'similar')
                    self.assertEqual(p['image_url'], f'/images/tshirt/{p["product_id"]}.jpg')
        self.assertEqual(self.raw, original)

    def test_optional_analysis_passes_through_without_debug_trace(self):
        analysis = {"attributes": {"colors": {"label": "black", "score": .3,
            "runner_up": "navy blue", "runner_up_score": .2, "margin": .1,
            "used_for_filter": True}}, "filters_used": {"colors": "black"},
            "strategy": "attribute_guided_visual"}
        self.raw.update(image_analysis=analysis, diagnostics={"internal": "debug only"})
        body = self.upload().json()
        self.assertEqual(body['image_analysis'], analysis)
        self.assertNotIn('diagnostics', body)
        self.assertTrue({'text', 'search_type', 'products', 'closing_text'} <= body.keys())
        self.search.search_by_image.assert_not_called()

    def test_missing_upload_and_invalid_limits(self):
        self.assertEqual(self.client.post('/api/image-search').status_code, 422)
        for value in ('0', '9', '-1', '1.5', 'no'):
            self.assertEqual(self.upload(data={'limit': value}).status_code, 422)
        self.factory.assert_not_called()

    def test_requested_limit_and_empty_results(self):
        response = self.upload(data={'limit': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['products']), 1)
        self.assertEqual(self.search.search_by_image_hybrid.call_args.kwargs['limit'], 1)
        self.search.search_by_image_hybrid.return_value = {'results': []}
        body = self.upload().json()
        self.assertEqual(body['products'], [])
        self.assertEqual(body['closing_text'], '')
        self.assertIn('No visually', body['text'])

    def test_fake_corrupt_empty_unsupported_and_mime(self):
        gif = image_bytes('GIF')
        for data, mime in ((b'text', 'image/jpeg'), (b'\xff\xd8\xffbroken', 'image/jpeg'),
                           (b'', 'image/png'), (b'%PDF-1.7', 'application/pdf'),
                           (b'PK\x03\x04', 'application/zip'), (gif, 'image/png'),
                           (image_bytes(), 'text/plain')):
            with self.subTest(mime=mime):
                self.assertEqual(self.upload(data, mime).status_code, 400)
        self.factory.assert_not_called()

    def test_size_limit_and_pixel_limit(self):
        self.assertEqual(self.upload(b'x' * (MAX_IMAGE_BYTES + 1)).status_code, 413)
        self.assertEqual(self.upload(b'x' * (MAX_MULTIPART_BYTES + 1)).status_code, 413)
        with patch('src.image_upload.MAX_IMAGE_PIXELS', 100):
            self.assertEqual(self.upload().status_code, 400)
        self.factory.assert_not_called()

    def test_backend_failure_does_not_leak(self):
        self.search.search_by_image_hybrid.side_effect = RuntimeError('secret-token /private/path')
        response = self.upload()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret', response.text)
        self.assertNotIn('/private', response.text)

    def test_initialization_failure_closes_image(self):
        self.factory.side_effect = api.HTTPException(503, 'Image search unavailable.')
        self.assertEqual(self.upload().status_code, 503)

    def test_body_limit_without_content_length(self):
        async def run():
            downstream = Mock()
            messages = iter([{'type': 'http.request', 'body': b'x'*8, 'more_body': True},
                             {'type': 'http.request', 'body': b'x'*8, 'more_body': False}])
            sent = []
            async def receive():
                return next(messages)
            async def send(message):
                sent.append(message)
            with patch('src.image_upload.MAX_MULTIPART_BYTES', 10):
                await ImageUploadSizeLimit(downstream)(
                    {'type':'http','path':'/api/image-search','headers':[]}, receive, send)
            downstream.assert_not_called()
            self.assertEqual(sent[0]['status'], 413)
        asyncio.run(run())


class ImageLifecycleTests(TestCase):
    def test_reuses_existing_agent_search_without_loading_model(self):
        existing = object()
        with patch.object(api, '_agent', Mock(product_search=existing)), patch.object(api, '_image_search', None):
            self.assertIs(api._get_image_search(), existing)
            self.assertIs(api._get_image_search(), existing)

    def test_image_first_search_is_injected_into_later_chat_agent(self):
        import sys
        from types import SimpleNamespace
        search = object()
        constructor = Mock()
        with patch.object(api, '_image_search', search), patch.dict(
            sys.modules, {'chatbot': SimpleNamespace(GarmentAgent=constructor)}), patch.dict(
            api.os.environ, {'OPENAI_MODEL':'test', 'QDRANT_URL':'test',
                             'QDRANT_COLLECTION':'test', 'POE_API':'test'}):
            api._create_agent()
        constructor.assert_called_once_with(product_search=search)

    def test_independent_singleton_does_not_require_agent(self):
        import sys
        from types import SimpleNamespace
        factory = Mock(return_value=object())
        with patch.object(api, '_agent', None), patch.object(api, '_image_search', None), patch.dict(
            sys.modules, {'src.product_search': SimpleNamespace(ProductSearch=factory)}):
            first = api._get_image_search()
            self.assertIs(api._get_image_search(), first)
            factory.assert_called_once_with()


if __name__ == '__main__':
    main()
