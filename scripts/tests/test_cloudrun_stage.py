import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'stage_cloudrun_frontend.py'
spec = importlib.util.spec_from_file_location('cloudstage', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CloudStageTests(unittest.TestCase):
    def test_cloud_staging_preserves_working_mac_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'frontend').mkdir()
            old="export const API_BASE_URL = 'https://working.trycloudflare.com';\n"
            (root/'frontend/config.js').write_text(old)
            (root/'frontend/index.html').write_text('<html>Existing UI</html>')
            (root/'frontend/fake.test.js').write_text('excluded')
            (root/'firebase.json').write_text('{"hosting":{"public":"frontend"}}')
            (root/'.firebaserc').write_text('{"projects":{"default":"garmentchatbot"}}')
            with patch.object(module,'ROOT',root):
                target=module.stage('https://verified-cloud.run.app')
            self.assertEqual((root/'frontend/config.js').read_text(),old)
            self.assertIn('https://verified-cloud.run.app',(target/'public/config.js').read_text())
            self.assertEqual((target/'public/index.html').read_text(),'<html>Existing UI</html>')
            self.assertFalse((target/'public/fake.test.js').exists())

    def test_untrusted_or_non_https_origin_is_rejected(self):
        for origin in ('http://cloud.run.app','https://other.example',"https://evil'.run.app",'https://key@cloud.run.app','https://cloud.run.app/api'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):module.stage(origin)
