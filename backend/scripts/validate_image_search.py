"""Read-only live image retrieval audit; no LLM, ingestion, collection writes or uploads."""
import argparse
import base64
import html
import json
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.asset_paths import IMAGE_ROOT, resolve_catalog_path


class ValidationError(ValueError):
    """Only locally authored, credential-free validation messages."""


def local_path(value):
    path = Path(value)
    return resolve_catalog_path(path)


def image_tag(value):
    path = local_path(value)
    # Gallery can embed only existing dataset images, never arbitrary payload paths.
    try:
        path.resolve().relative_to(IMAGE_ROOT)
    except ValueError:
        return '<p>Image outside dataset; inspect original path separately.</p>'
    if not path.is_file():
        return '<p>Image unavailable</p>'
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return f'<img src="data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}" alt="Garment reference">'


def write_gallery(report, destination):
    rows = []
    for run in report['queries']:
        cards = [f'<figure>{image_tag(run["query_image"])}<figcaption>Query: {html.escape(run["query_image"])}</figcaption></figure>']
        for p in run['without_self']:
            caption = f'ID {p["product_id"]} · score {p["similarity_score"]:.4f} · {p["image_path"]}'
            cards.append(f'<figure>{image_tag(p["image_path"])}<figcaption>{html.escape(caption)}</figcaption></figure>')
        rows.append(f'<h2>{html.escape(run["query_image"])}</h2><p>Self rank: {run["self_rank"]}; score: {run["self_score"]}</p><section>{"".join(cards)}</section>')
    destination.write_text('<!doctype html><meta charset="utf-8"><title>Image search validation</title>'
        '<style>body{font:15px system-ui;margin:24px}section{display:flex;gap:12px;overflow-x:auto}'
        'figure{margin:0;flex:0 0 170px}img{width:170px;height:220px;object-fit:contain;background:#f5f5f5}'
        'figcaption{font-size:12px;overflow-wrap:anywhere}h2{margin-top:32px}</style>'
        '<h1>Real image search — query followed by ranked results excluding self</h1>'
        '<p>Original dataset images. No image editing, quality cutoff or reranking.</p>' + ''.join(rows), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+')
    parser.add_argument('--limit', type=int, choices=range(5, 9), default=8,
                        help='Candidates after removing self (5–8; default 8).')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--gallery', type=Path)
    args = parser.parse_args()
    # Validate paths/decode before expensive model loading, using PIL only for validation.
    from PIL import Image
    for value in args.images:
        if not local_path(value).is_file():
            raise ValidationError('Query image does not exist or is not a file.')
        try:
            with Image.open(local_path(value)) as image:
                image.verify()
        except OSError:
            raise ValidationError('Query image could not be decoded as a supported image.') from None

    import numpy as np
    from src.product_search import ProductSearch
    search = ProductSearch()  # One existing embedder shared across all queries.
    collection = search.client.get_collection(search.collection_name)
    params = collection.config.params.vectors
    if isinstance(params, dict):
        raise ValidationError('This validator expects the existing unnamed image-vector collection.')
    report = {'model': search.embedder.model_name, 'collection': search.collection_name,
              'collection_dimension': params.size, 'distance': params.distance.value, 'queries': []}
    print(json.dumps({k:v for k,v in report.items() if k != 'queries'}, ensure_ascii=False))
    for value in args.images:
        # One extra candidate permits removing self without changing original order.
        result = search.search_by_image_path(value, limit=args.limit + 1)
        own = [p for p in result['results'] if p.get('image_path') and
               local_path(p['image_path']).resolve() == local_path(value).resolve()]
        source = own[0] if own else None
        others = [p for p in result['results'] if not source or
                  (p['point_id'] != source['point_id'] and
                   (source.get('product_id') is None or str(p.get('product_id')) != str(source['product_id'])))]
        vector = search.embedder.embed_image(local_path(value))
        if len(vector) != params.size or not np.isclose(np.linalg.norm(vector), 1, atol=1e-5):
            raise ValidationError('Image vector dimension or normalization does not match the collection.')
        row = {**result, 'query_vector_norm': float(np.linalg.norm(vector)),
               'self_rank': result['results'].index(source)+1 if source else None,
               'self_score': source['similarity_score'] if source else None,
               'top_result': result['results'][0] if result['results'] else None,
               'without_self': others[:args.limit]}
        if source:
            stored = search.client.retrieve(search.collection_name, ids=[source['point_id']], with_vectors=True)[0]
            stored_vector = np.asarray(stored.vector, dtype=np.float32)
            row['stored_vector_cosine'] = float(np.dot(vector, stored_vector) / np.linalg.norm(stored_vector))
            row['stored_embedding_model'] = (stored.payload or {}).get('embedding_model')
        report['queries'].append(row)
        print(f'\nQuery: {value}\nDimension: {len(vector)}; self rank: {row["self_rank"]}; self score: {row["self_score"]}')
        if row['top_result']:
            p = row['top_result']
            print(f'Top: product_id={p["product_id"]} point_id={p["point_id"]} score={p["similarity_score"]:.4f}')
        for index, p in enumerate(row['without_self'], 1):
            print(f'{index}. product_id={p["product_id"]} score={p["similarity_score"]:.4f} image={p["image_path"]}')
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    if args.gallery:
        write_gallery(report, args.gallery)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except ValidationError as exc:
        # Controlled local validation errors; these messages contain no credentials.
        print(f'Validation failed: {exc}', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f'Image search failed ({type(exc).__name__}); check model/service configuration.', file=sys.stderr)
        sys.exit(1)
