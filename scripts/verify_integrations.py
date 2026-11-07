"""Read-only checks using NEW injected credentials; never loads backend/.env.

Run from repository root. --models downloads/loads models, --llm sends one
billable minimal request. Neither option runs a product search or writes Qdrant.
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', action='store_true')
    parser.add_argument('--llm', action='store_true')
    args = parser.parse_args()
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    required = ['QDRANT_URL', 'QDRANT_COLLECTION', 'CLIP_MODEL']
    if any(not os.getenv(name, '').strip() for name in required):
        raise RuntimeError('Inject approved Qdrant and model environment settings first')
    from qdrant_client import QdrantClient
    from src.asset_paths import resolve_catalog_path, IMAGE_ROOT
    client = QdrantClient(url=os.environ['QDRANT_URL'],
                          api_key=os.getenv('QDRANT_API') or None, timeout=10)
    try:
        info = client.get_collection(os.environ['QDRANT_COLLECTION'])
        vectors = info.config.params.vectors
        if isinstance(vectors, dict) or vectors.size != 512 or str(vectors.distance).lower() != 'cosine':
            raise RuntimeError('Expected unnamed 512-dimensional cosine vectors')
        if not info.points_count:
            raise RuntimeError('Collection is empty')
        records, _ = client.scroll(os.environ['QDRANT_COLLECTION'], limit=16,
                                   with_payload=True, with_vectors=False)
        for record in records:
            payload = record.payload or {}
            if not isinstance(payload.get('product_id'), (str, int)):
                raise RuntimeError('Sample payload lacks product_id')
            path = resolve_catalog_path(payload.get('image_url', ''))
            path.resolve().relative_to(IMAGE_ROOT)
            if not path.is_file():
                raise RuntimeError('Sample image missing; reconcile catalog without re-ingestion')
            for key in ('colors', 'patterns', 'neckline', 'sleeve', 'style'):
                if key in payload and not isinstance(payload[key], (str, list)):
                    raise RuntimeError('Sample attribute has unexpected type')
        print('PASS: Qdrant collection shape, populated count and sampled image paths (not a full payload audit)')
    finally:
        client.close()
    if args.models:
        from src.extract_embeding import FashionClipEmbedder
        from sentence_transformers import SentenceTransformer
        model = FashionClipEmbedder()
        vector = model.embed_texts(['plain t-shirt'])
        if vector.shape != (1, 512):
            raise RuntimeError('Model output dimension mismatch')
        with __import__('PIL.Image', fromlist=['Image']).open(IMAGE_ROOT / 'tshirt' / '1.jpg') as image:
            if model.embed_pil_image(image).shape != (512,):
                raise RuntimeError('Image embedding dimension mismatch')
        SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').encode(['plain t-shirt'])
        print('PASS: FashionCLIP text/image and MiniLM inference; ingestion model identity still requires owner confirmation')
    if args.llm:
        import openai
        if not os.getenv('OPENAI_MODEL'):
            raise RuntimeError('OPENAI_MODEL missing')
        with openai.OpenAI(api_key=os.getenv('POE_API') or os.getenv('OPENAI_API_KEY'),
                           base_url=os.getenv('POE_URL') or None,
                           timeout=30, max_retries=0) as provider:
            response = provider.responses.create(model=os.environ['OPENAI_MODEL'],
                input='Reply with OK.', max_output_tokens=32)
            if not response.output_text.strip():
                raise RuntimeError('Provider returned no text')
        print('PASS: minimal Responses API request; actual structured-tool chatbot E2E still required')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # SDK exceptions may contain secrets, endpoint strings or payloads.
        print('FAIL: integration check (' + type(exc).__name__ + '). Check private configuration.', file=sys.stderr)
        sys.exit(1)
