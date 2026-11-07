"""Cloud Run process entry point. Model/retrieval code remains unchanged."""
import json
import os
from pathlib import Path
import sys


def main():
    required = ('POE_API', 'POE_URL', 'OPENAI_MODEL', 'QDRANT_URL',
                'QDRANT_API', 'QDRANT_COLLECTION', 'CLIP_MODEL', 'CORS_ORIGINS')
    missing = [name for name in required if not os.getenv(name, '').strip()]
    if missing:
        raise RuntimeError('Missing server settings: ' + ', '.join(missing))
    models = json.loads((Path(__file__).parent / 'models.json').read_text())
    if os.environ['CLIP_MODEL'] not in models:
        raise RuntimeError('Runtime CLIP_MODEL differs from baked model assets')
    if not all(origin.strip().startswith('https://') for origin in os.environ['CORS_ORIGINS'].split(',')):
        raise RuntimeError('Cloud Run CORS requires explicit HTTPS frontend origins')
    if '*' in os.environ['CORS_ORIGINS']:
        raise RuntimeError('Wildcard production CORS is not allowed')
    sys.path.insert(0, '/app/backend')
    import uvicorn
    # Liveness stays independent of model initialization. First real request loads models.
    uvicorn.run('api:app', host='0.0.0.0', port=int(os.getenv('PORT', '8080')),
                workers=1, timeout_keep_alive=5, access_log=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not echo private config or downstream exception bodies.
        print('Cloud Run startup failed (' + type(exc).__name__ + '). Check server settings.', file=sys.stderr)
        raise SystemExit(1)
