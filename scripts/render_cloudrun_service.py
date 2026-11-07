"""Render a secret-free Cloud Run manifest; never deploy or change Firebase."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-digest', required=True)
    parser.add_argument('--runtime-service-account', required=True)
    parser.add_argument('--poe-secret-version', required=True)
    parser.add_argument('--qdrant-secret-version', required=True)
    args = parser.parse_args()
    if '@sha256:' not in args.image_digest:
        parser.error('Use a verified immutable Artifact Registry digest')
    if not args.runtime_service_account.endswith('@garmentchatbot.iam.gserviceaccount.com'):
        parser.error('Use the actual dedicated runtime service account in garmentchatbot')
    if not args.poe_secret_version.isdecimal() or not args.qdrant_secret_version.isdecimal():
        parser.error('Use actual numeric Secret Manager versions')
    env = dotenv_values(ROOT / '.env.cloudrun', interpolate=False)
    required = ('POE_API', 'POE_URL', 'OPENAI_MODEL', 'QDRANT_URL', 'QDRANT_API', 'QDRANT_COLLECTION', 'CLIP_MODEL')
    missing = [key for key in required if not env.get(key, '').strip()]
    if missing:
        parser.error('Missing private settings: ' + ', '.join(missing))
    for key in ('POE_URL', 'QDRANT_URL'):
        parsed = urlparse(env[key])
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query:
            parser.error(key + ' must be HTTPS without embedded credentials/query')
    manifest = yaml.safe_load((ROOT / 'deployment/cloudrun/service.yaml').read_text())
    spec = manifest['spec']['template']['spec']
    spec['serviceAccountName'] = args.runtime_service_account
    container = spec['containers'][0]
    container['image'] = args.image_digest
    for item in container['env']:
        if item['name'] == 'POE_API': item['valueFrom']['secretKeyRef']['key'] = args.poe_secret_version
        if item['name'] == 'QDRANT_API': item['valueFrom']['secretKeyRef']['key'] = args.qdrant_secret_version
    for key in ('POE_URL', 'OPENAI_MODEL', 'QDRANT_URL', 'QDRANT_COLLECTION', 'CLIP_MODEL'):
        container['env'].append({'name': key, 'value': env[key]})
    output = ROOT / '.runtime/cloudrun/service.ready.yaml'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(manifest, sort_keys=False))
    # Secret values are checked, but never serialized into the manifest.
    assert env['POE_API'] not in output.read_text()
    assert env['QDRANT_API'] not in output.read_text()
    print('Rendered only; no cloud changes:', output)


if __name__ == '__main__':
    main()
