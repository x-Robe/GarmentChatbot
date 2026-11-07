"""Stage an HTTPS Cloud Run frontend without modifying Mac rollback or Firebase."""
import argparse
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def stage(origin):
    parsed = urlparse(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.run.app')
            or not re.fullmatch(r'[a-zA-Z0-9.-]+', parsed.hostname)
            or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('Use the actual plain HTTPS *.run.app service origin')
    target = ROOT / '.runtime/cloudrun/frontend'
    public = target / 'public'
    public.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / 'frontend').iterdir():
        if source.is_file() and source.suffix in ('.html', '.css', '.js') and not source.name.endswith('.test.js'):
            shutil.copy2(source, public / source.name)
    config = public / 'config.js'
    text, count = re.subn(r"export const API_BASE_URL = '[^']*';",
                          "export const API_BASE_URL = '" + origin.rstrip('/') + "';", config.read_text())
    if count != 1:
        raise ValueError('Unexpected frontend config shape')
    config.write_text(text)
    hosting = json.loads((ROOT / 'firebase.json').read_text())
    hosting['hosting']['public'] = 'public'
    (target / 'firebase.json').write_text(json.dumps(hosting, indent=2) + '\n')
    shutil.copy2(ROOT / '.firebaserc', target / '.firebaserc')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True)
    args = parser.parse_args()
    print('Staged only; public Firebase and working Mac config unchanged:', stage(args.api_url))
