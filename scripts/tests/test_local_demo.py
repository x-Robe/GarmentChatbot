import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'local_demo.py'
spec = importlib.util.spec_from_file_location('demo', SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

class DemoTests(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Missing private settings'):
            demo.validate_live({})

    def test_settings_do_not_load_backend_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env.local').write_text('OPENAI_MODEL=local-choice\n')
            (root / '.env.local').chmod(0o600)
            with patch.object(demo, 'ROOT', root), patch.dict(os.environ, {'OPENAI_MODEL': 'injected-choice'}, clear=True):
                env = demo.settings()
            self.assertEqual(env['OPENAI_MODEL'], 'injected-choice')
            self.assertEqual(env['PYTHON_DOTENV_DISABLED'], '1')
            self.assertIn('https://garmentchatbot.web.app', env['CORS_ORIGINS'])

    def test_historical_secret_refused_without_echo(self):
        secret = 'owned-test-key-0123456789'
        with patch.object(demo.subprocess, 'check_output', return_value='abc\n'), patch.object(demo.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ('POE_API=' + secret).encode()
            with self.assertRaises(ValueError) as error:
                demo.reject_historical_secrets({'POE_API': secret})
            self.assertNotIn(secret, str(error.exception))

    def test_history_exception_requires_explicit_option(self):
        env = {'POE_API': 'owned-test-key', 'POE_URL': 'https://api.poe.com/v1',
               'OPENAI_MODEL': 'owned-model', 'QDRANT_URL': 'https://owned.example',
               'QDRANT_API': 'owned-database-key', 'QDRANT_COLLECTION': 'owned',
               'CLIP_MODEL': 'owned-model', 'CORS_ORIGINS': 'https://garmentchatbot.web.app'}
        with patch.object(demo, 'reject_historical_secrets', side_effect=ValueError('known exposure')):
            with self.assertRaisesRegex(ValueError, 'known exposure'):
                demo.validate_live(env)
            demo.validate_live(env, allow_historical=True)

    def test_stage_preserves_ui_and_excludes_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frontend = root / 'frontend'
            frontend.mkdir()
            original = "export const API_BASE_URL = 'https://old.example';\nexport const CONTEXT_LIMITS = {};\n"
            (frontend / 'config.js').write_text(original)
            (frontend / 'index.html').write_text('<html>Existing UI</html>')
            (frontend / 'foo.test.js').write_text('not published')
            (frontend / '.env').write_text('not published')
            (root / 'firebase.json').write_text('{"hosting":{"public":"frontend"}}')
            (root / '.firebaserc').write_text('{"projects":{"default":"garmentchatbot"}}')
            runtime = root / '.runtime'; runtime.mkdir()
            with patch.object(demo, 'ROOT', root), patch.object(demo, 'RUNTIME', runtime):
                public = demo.configure_frontend('https://owned.trycloudflare.com')
            self.assertEqual((public / 'index.html').read_text(), '<html>Existing UI</html>')
            self.assertIn('https://owned.trycloudflare.com', (public / 'config.js').read_text())
            self.assertNotIn('old.example', (frontend / 'config.js').read_text())
            self.assertFalse((public / '.env').exists())
            self.assertFalse((public / 'foo.test.js').exists())
            self.assertEqual((runtime / 'frontend-config.original.js').read_text(), original)

    def test_reject_insecure_or_injected_origins(self):
        for origin in ['http://plain.example', 'https://user:password@example.com', "https://evil';alert(1)", 'https://example.com/api']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                demo.configure_frontend(origin)
