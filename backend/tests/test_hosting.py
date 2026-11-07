"""Offline deployment transport checks; no live services."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api
from src.hosting_limits import HostingLimits

class HostingTests(unittest.TestCase):
    def test_cold_readiness(self):
        with patch.object(api, '_agent', None), patch.object(api, '_image_search', None), patch.object(api, '_create_agent') as create:
            with TestClient(api.app) as client:
                self.assertEqual(client.get('/api/health').status_code, 200)
                self.assertEqual(client.get('/api/ready').status_code, 503)
            create.assert_not_called()

    def test_warm_readiness(self):
        search = Mock()
        search.embedder.model.config.projection_dim = 512
        info = SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=512, distance='Cosine'))), points_count=10)
        search.client.get_collection.return_value = info
        with patch.object(api, '_agent', None), patch.object(api, '_image_search', search):
            with TestClient(api.app) as client:
                self.assertEqual(client.get('/api/ready').json(), {'status': 'ready', 'llm_verified': False})
                info.config.params.vectors.size = 768
                self.assertEqual(client.get('/api/ready').status_code, 503)

    def test_rate_limit(self):
        app = FastAPI()
        with patch.dict(os.environ, {'API_REQUESTS_PER_MINUTE': '1'}):
            app.add_middleware(HostingLimits)
            @app.post('/api/chat')
            def chat(): return {'ok': True}
            @app.get('/api/health')
            def health(): return {'ok': True}
            with TestClient(app) as client:
                self.assertEqual(client.post('/api/chat').status_code, 200)
                response = client.post('/api/chat')
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers['retry-after'], '60')
                self.assertEqual(client.get('/api/health').status_code, 200)

    def test_concurrency(self):
        async def run():
            started, release = asyncio.Event(), asyncio.Event()
            async def app(scope, receive, send):
                started.set()
                await release.wait()
            middleware = HostingLimits(app)
            middleware.capacity = 1
            scope = {'type': 'http', 'method': 'POST', 'path': '/api/chat'}
            messages = []
            async def receive(): return {'type': 'http.request'}
            async def send(message): messages.append(message)
            first = asyncio.create_task(middleware(scope, receive, send))
            await started.wait()
            await middleware(scope, receive, send)
            self.assertEqual(messages[0]['status'], 429)
            release.set()
            await first
            self.assertEqual(middleware.inflight, 0)
        asyncio.run(run())
