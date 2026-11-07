"""Real repository assets/HTTP serving, with no models, provider or hosted Qdrant."""
import csv
import hashlib
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import api
from src.asset_paths import BACKEND_ROOT, REPOSITORY_ROOT, IMAGE_ROOT, resolve_catalog_path
from src.product_search import ProductSearch


class RepositoryLayoutTests(unittest.TestCase):
    def test_repository_paths_schema_and_skill(self):
        self.assertEqual(api.IMAGE_ROOT, REPOSITORY_ROOT / "data/images")
        self.assertEqual(BACKEND_ROOT, REPOSITORY_ROOT / "backend")
        self.assertTrue((BACKEND_ROOT / "data/samples/sample_tshirt_schema.json").is_file())
        self.assertTrue((BACKEND_ROOT / "SKILL.md").read_text().strip())
        self.assertFalse((BACKEND_ROOT / "data/images").exists())
        self.assertEqual(resolve_catalog_path("query.jpg"), BACKEND_ROOT / "query.jpg")

    def test_all_catalog_files_match_release_manifest(self):
        with (REPOSITORY_ROOT / "docs/CATALOG_ASSET_MANIFEST.csv").open() as file:
            rows = list(csv.DictReader(file))
        files = list(IMAGE_ROOT.glob("tshirt/*.jpg"))
        self.assertEqual(len(rows), 1993)
        self.assertEqual({file.name for file in files}, {Path(row["relative_path"]).name for row in rows})
        for row in rows:
            path = resolve_catalog_path(row["relative_path"])
            self.assertEqual(path.stat().st_size, int(row["bytes"]))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
        for identifier in range(357, 364):
            self.assertFalse((IMAGE_ROOT / f"tshirt/{identifier}.jpg").exists())

    def test_real_health_catalog_images_and_mapping(self):
        with TestClient(api.app) as client, patch.object(api, "_create_agent") as factory:
            self.assertEqual(client.get("/api/health").json(), {"status": "ok"})
            for identifier in (1, 941, 2000):
                path = resolve_catalog_path(f"data/images/tshirt/{identifier}.jpg")
                url = api.image_url_for(f"data/images/tshirt/{identifier}.jpg")
                self.assertEqual(url, f"/images/tshirt/{identifier}.jpg")
                self.assertEqual(api.image_url_for(str(path)), url)
                response = client.get(url, headers={"Origin": "http://127.0.0.1:8000"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, path.read_bytes())
                self.assertEqual(response.headers["content-type"], "image/jpeg")
                self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:8000")
            self.assertEqual(client.get("/images/tshirt/357.jpg").status_code, 404)
            factory.assert_not_called()

    def test_query_ingestion_and_evaluation_share_existing_catalog(self):
        relative = "data/images/tshirt/941.jpg"
        search = ProductSearch.__new__(ProductSearch)
        search.search_by_image = Mock(return_value={"results": []})
        self.assertEqual(search.search_by_image_path(relative), {"query_image": relative, "results": []})
        search.search_by_image.assert_called_once()
        # Import offline helper definitions without running ingestion or retrieval.
        with patch.object(sys, "path", [str(BACKEND_ROOT / "src"), str(REPOSITORY_ROOT / "evaluation"), *sys.path]):
            ingestion = runpy.run_path(str(BACKEND_ROOT / "src/ingest_product.py"), run_name="layout_import_check")
            evaluation = runpy.run_path(str(REPOSITORY_ROOT / "evaluation/run_evaluation.py"), run_name="layout_import_check")
        self.assertEqual(ingestion["validate_product"]({"id": "941", "image_path": relative}), resolve_catalog_path(relative).resolve())
        self.assertEqual(evaluation["image_path"](relative), resolve_catalog_path(relative).resolve())
