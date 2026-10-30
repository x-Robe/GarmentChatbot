"""Read-only baseline/hybrid comparison; one image embedding per query, no LLM."""
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
from PIL import Image
from src.product_search import ProductSearch
from src.zero_shot_classifier import ATTRIBUTE_LABELS, PROMPT_TEMPLATES
from src.hybrid_image_search import CANDIDATE_POOL_MULTIPLIER, MAX_HARD_FILTERS, MIN_ATTRIBUTE_MARGIN, MIN_STYLE_MARGIN


def local_path(value):
    path = Path(value)
    return resolve_catalog_path(path)


def picture(value):
    path = local_path(value).resolve()
    # Only embed workspace images, never arbitrary paths from a payload.
    try:
        path.relative_to(ROOT.parent)
    except ValueError:
        return '<span>Image outside workspace</span>'
    if not path.is_file():
        return '<span>Image unavailable</span>'
    mime = mimetypes.guess_type(path.name)[0] or 'image/jpeg'
    return f'<img alt="{html.escape(path.name)}" src="data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}">'


def gallery(report, destination):
    esc = lambda value: html.escape(str(value))
    sections = []
    for run in report['queries']:
        analysis = run['hybrid']['image_analysis']
        text = f'<h2>{esc(run["query_image"])} ({esc(run["source_type"])})</h2><figure class="query">{picture(run["query_image"])}</figure>'
        text += '<pre>' + esc(json.dumps(analysis, ensure_ascii=False, indent=2)) + '</pre>'
        for key, title in [('baseline', 'BASELINE — Pure Image Similarity'), ('hybrid', 'HYBRID — Attribute Guided')]:
            text += f'<h3>{title}</h3><div class="grid">'
            for index, p in enumerate(run[key]['results'], 1):
                text += f'<figure>{picture(p["image_path"])}<figcaption>{index}. ID {esc(p["product_id"])} · {p["similarity_score"]:.4f}<br>{esc(p["image_path"])}<br>{esc(json.dumps(p["attributes"],ensure_ascii=False))}</figcaption></figure>'
            text += '</div>'
        sections.append(text)
    destination.write_text('<!doctype html><meta charset="utf-8"><title>Hybrid image search comparison</title><style>body{font:14px system-ui;margin:24px;max-width:1100px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}figure{margin:0}img{width:100%;height:240px;object-fit:contain;background:#fafafa}.query{width:220px}figcaption{font-size:12px;overflow-wrap:anywhere}pre{white-space:pre-wrap;font-size:12px}h2{border-top:2px solid #ddd;padding-top:24px}</style><h1>Baseline / Hybrid — original reference images</h1><p>Cosine scores are not probabilities. Payload agreement measures pipeline consistency, not independent accuracy. Dataset self-matches remain included; compare other candidates too.</p>'+''.join(sections),encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='*', default=['data/images/tshirt/646.jpg','data/images/tshirt/635.jpg','data/images/tshirt/442.jpg','../assets/demo/design_001.svg.png','../assets/demo/design_006.svg.png'])
    parser.add_argument('--output', type=Path, default=ROOT/'validation/hybrid_image_results.json')
    parser.add_argument('--gallery', type=Path, default=ROOT/'validation/hybrid_image_gallery.html')
    args = parser.parse_args()
    search = ProductSearch()
    report = {'model': search.embedder.model_name, 'collection': search.collection_name,
              'labels': ATTRIBUTE_LABELS, 'prompts': PROMPT_TEMPLATES,
              'policy': {'pool_multiplier': CANDIDATE_POOL_MULTIPLIER, 'max_filters': MAX_HARD_FILTERS,
                         'min_margin': MIN_ATTRIBUTE_MARGIN, 'style_min_margin': MIN_STYLE_MARGIN}, 'queries': []}
    for name in args.images:
        with Image.open(local_path(name)) as image:
            vector = search.embedder.embed_pil_image(image)
        baseline = search.search_by_image_vector_only(vector, limit=8)
        hybrid = search.search_by_image_vector_hybrid(vector, limit=8, include_diagnostics=True)
        run = {'query_image': name, 'source_type': 'dataset' if 'data/images/' in name else 'non-dataset illustration',
               'baseline': baseline, 'hybrid': hybrid}
        report['queries'].append(run)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(name, json.dumps(hybrid['image_analysis'], ensure_ascii=False), flush=True)
    gallery(report, args.gallery)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Validation failed ({type(exc).__name__}); check local configuration.', file=sys.stderr)
        sys.exit(1)
