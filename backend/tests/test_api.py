"""Transport tests with a fake agent; never import the model/search stack."""

import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.agent = Mock()
        self.agent.respond.return_value = {
            "requested_mode": None, "effective_mode": None, "effective_image_strategy": None,
            "requested_count": None, "effective_count": None, "count_capped": False,
            "search_type": None, "continuation": None, "text_overrides": None, "image_analysis": None,
            "text": "Backend reply", "response_id": "resp_test",
            "active_search": None, "relation_to_context": None, "has_more": None,
            "products": [], "search_results": {"exact": [], "similar": []},
            "closing_text": "", "resolved_query": "", "search_strategy": "none", "intent": "search",
        }
        self.factory_patch = patch.object(api, "_create_agent", return_value=self.agent)
        self.factory = self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.agent_patch = patch.object(api, "_agent", None)
        self.agent_patch.start()
        self.addCleanup(self.agent_patch.stop)
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)

    def test_health_does_not_load_agent(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.factory.assert_not_called()

    def test_modes_delegate_and_reuse_agent(self):
        for mode in ("auto", "default", "exact", "similar"):
            with self.subTest(mode="auto" if mode == "default" else mode):
                response = self.client.post("/api/chat", json={"query": "black t-shirt", "mode": mode})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), self.agent.respond.return_value)
                self.agent.respond.assert_called_with(query="black t-shirt", mode="auto" if mode == "default" else mode)
        self.factory.assert_called_once_with()

    def test_mode_defaults(self):
        response = self.client.post("/api/chat", json={"query": "black t-shirt"})
        self.assertEqual(response.status_code, 200)
        self.agent.respond.assert_called_once_with(query="black t-shirt", mode="auto")

    def test_structured_results_are_preserved(self):
        product = {
            "point_id": "point-1", "product_id": "123", "similarity_score": 0.91,
            "image_path": "data/images/123.jpg", "attributes": {"colors": ["black"]},
            "label_matches": {"colors": True},
        }
        for mode, kinds in (("exact", ["exact"]), ("similar", ["similar"]),
                            ("default", ["exact", "similar"])):
            with self.subTest(mode="auto" if mode == "default" else mode):
                self.agent.respond.return_value.update(
                    products=[{**product, "match_type": kind} for kind in kinds],
                    search_results={kind: [product] if kind in kinds else []
                                    for kind in ("exact", "similar")},
                )
                response = self.client.post("/api/chat", json={"query": "tee", "mode": mode})
                self.assertEqual(response.status_code, 200)
                expected = deepcopy(self.agent.respond.return_value)
                for products in (expected["products"], *expected["search_results"].values()):
                    for item in products:
                        item["image_url"] = "/images/123.jpg"
                self.assertEqual(response.json(), expected)

    def test_route_intent_and_closing_are_preserved(self):
        self.agent.respond.return_value.update(
            closing_text="Try darker shades.", search_strategy="both", intent="search")
        response = self.client.post("/api/chat", json={"query": "tee", "mode": "auto"})
        self.assertEqual(response.json(), self.agent.respond.return_value)
        self.agent.respond.return_value.update(
            closing_text="", search_strategy="none", intent="informational")
        response = self.client.post("/api/chat", json={"query": "What is a mock neck?"})
        self.assertEqual(response.json(), self.agent.respond.return_value)

    def test_optional_context_delegates_compact_text(self):
        context = [{"role":"user", "text":"Japanese streetwear t-shirts"},
                   {"role":"assistant", "text":"Try a darker look."}]
        self.agent.respond.return_value['resolved_query'] = 'dark Japanese streetwear t-shirts'
        response = self.client.post('/api/chat', json={"query":"make them darker", "context":context})
        self.assertEqual(response.status_code, 200)
        self.agent.respond.assert_called_once_with(query='make them darker', mode='auto', context=context)
        self.assertEqual(response.json()['resolved_query'], 'dark Japanese streetwear t-shirts')

    def test_bad_context_is_rejected_without_agent(self):
        for context in ([{"role":"system", "text":"secret"}], [{"role":"user", "text":"x"*10001}],
                        [{"role":"user", "text":"tee"}]*1001, [{"role":"user", "text":"tee", "products":[]}],
                        [{"role":"user", "text":123}], None, 'text'):
            response = self.client.post('/api/chat', json={"query":"more", "context":context})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn('secret', response.text)
        self.factory.assert_not_called()

    def test_real_static_image_and_cors(self):
        # The public release deliberately excludes catalog assets. Exercise the
        # actual static route/CORS using an owned, ephemeral JPEG instead.
        from PIL import Image
        from fastapi.staticfiles import StaticFiles
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tshirt").mkdir()
            with Image.new("RGB", (2, 2), "white") as image:
                image.save(root / "tshirt/1.jpg", format="JPEG")
            mount = next(route for route in api.app.routes if route.path == "/images")
            with patch.object(mount, "app", StaticFiles(directory=root)):
                response = self.client.get("/images/tshirt/1.jpg", headers={"Origin": "http://127.0.0.1:8000"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/jpeg")
            self.assertEqual(response.content, (root / "tshirt/1.jpg").read_bytes())
            self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:8000")
        self.factory.assert_not_called()

    def test_missing_image_and_private_paths_are_404(self):
        for url in ("/images/nonexistent-file.jpg", "/images/%2e%2e/%2e%2e/.env",
                    "/images/%2e%2e/%2e%2e/Credentials/", "/.env", "/api.py",
                    "/Credentials/", "/images/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_image_urls_preserve_agent_data_and_order(self):
        exact = {"product_id": "1", "image_path": "data/images/tshirt/1.jpg", "match_type": "exact"}
        similar = {"product_id": "2", "image_path": "data/images/tshirt/2.jpg", "match_type": "similar"}
        raw = {"text": "reply", "response_id": "r", "products": [exact, similar],
               "search_results": {"exact": [exact], "similar": [similar]}}
        original = deepcopy(raw)
        self.agent.respond.return_value = raw
        response = self.client.post("/api/chat", json={"query": "tee"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([p["match_type"] for p in body["products"]], ["exact", "similar"])
        for items in (body["products"], *body["search_results"].values()):
            for item in items:
                identifier = item["product_id"]
                self.assertEqual(item["image_url"], f"/images/tshirt/{identifier}.jpg")
                self.assertEqual(item["image_path"], f"data/images/tshirt/{identifier}.jpg")
        self.assertEqual(raw, original)

    def test_invalid_image_path_returns_null_url(self):
        self.agent.respond.return_value["products"] = [{"image_path": "../../secret.txt"}]
        response = self.client.post("/api/chat", json={"query": "tee"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["products"], [{"image_path": "../../secret.txt", "image_url": None}])

    def test_image_conversion_is_contained_and_escapes_url_characters(self):
        self.assertEqual(api.image_url_for(str(api.IMAGE_ROOT / "tshirt/1.jpg")), "/images/tshirt/1.jpg")
        self.assertEqual(api.image_url_for("data/images/tshirt/a #?.jpg"), "/images/tshirt/a%20%23%3F.jpg")
        for path in (None, 123, "", "../../secret.txt", "data/images/../../.env",
                     "data/images-other/file.jpg", "https://example.com/image.jpg",
                     str(api.PROJECT_ROOT / ".env"), "data/images", "data/images/\x00.jpg"):
            with self.subTest(path=path):
                self.assertIsNone(api.image_url_for(path))

    def test_symlink_escape_is_rejected(self):
        # Synthetic non-secret file; never read actual credentials in tests.
        with TemporaryDirectory() as directory:
            root = Path(directory) / "images"
            root.mkdir()
            outside = Path(directory) / "outside.txt"
            outside.write_text("outside")
            (root / "escape.jpg").symlink_to(outside)
            with patch.object(api, "IMAGE_ROOT", root):
                self.assertIsNone(api.image_url_for(str(root / "escape.jpg")))
            static = api.StaticFiles(directory=root, follow_symlink=False)
            test_app = api.FastAPI()
            test_app.mount("/images", static)
            with TestClient(test_app) as client:
                self.assertEqual(client.get("/images/escape.jpg").status_code, 404)

    def test_invalid_requests_do_not_load_agent(self):
        for body in ({}, {"query": ""}, {"query": " \n\t"}, {"query": None},
                     {"query": 123}, {"query": "tee", "mode": "abc"},
                     {"query": "tee", "mode": None}, ["tee"]):
            with self.subTest(body=body):
                response = self.client.post("/api/chat", json=body)
                self.assertEqual(response.status_code, 422)
                self.assertIsInstance(response.json()["detail"], str)
        self.factory.assert_not_called()

    def test_invalid_json(self):
        response = self.client.post("/api/chat", content="{", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.factory.assert_not_called()

    def test_backend_failure_is_sanitized(self):
        self.agent.respond.side_effect = RuntimeError("secret-key internal-host")
        response = self.client.post("/api/chat", json={"query": "tee"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-key", response.text)
        self.assertNotIn("internal-host", response.text)

    def test_invalid_backend_response_is_json_error(self):
        self.agent.respond.return_value = {"text": "missing response_id"}
        response = self.client.post("/api/chat", json={"query": "tee"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("detail", response.json())

    def test_missing_configuration(self):
        self.factory_patch.stop()
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post("/api/chat", json={"query": "tee"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("configuration", response.json()["detail"])

    def test_initialization_failure_can_retry(self):
        self.factory_patch.stop()
        constructor = Mock(side_effect=[RuntimeError("secret-key"), self.agent])
        env = {"POE_API": "test", "OPENAI_MODEL": "test", "QDRANT_URL": "test", "QDRANT_COLLECTION": "test"}
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"chatbot": SimpleNamespace(GarmentAgent=constructor)}):
            failed = self.client.post("/api/chat", json={"query": "tee"})
            self.assertEqual(failed.status_code, 503)
            self.assertNotIn("secret-key", failed.text)
            self.assertEqual(self.client.get("/api/health").status_code, 200)
            self.assertEqual(self.client.post("/api/chat", json={"query": "tee"}).status_code, 200)

    def test_cors(self):
        for origin, allowed in (("http://127.0.0.1:8000", True), ("https://untrusted.example", False)):
            response = self.client.options("/api/chat", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            self.assertEqual(response.status_code, 200 if allowed else 400)
            self.assertEqual(response.headers.get("access-control-allow-origin"), origin if allowed else None)


if __name__ == "__main__":
    unittest.main()
