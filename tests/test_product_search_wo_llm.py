import json

from src.product_search import ProductSearch


search = ProductSearch()

result = search.search(
    query=(
        "navy blue striped crew neck "
        "short sleeve t-shirt"
    ),
    filters={
        "colors": ["navy blue"],
        "patterns": ["striped"],
        "neckline": ["crew neck"],
        "sleeve": ["short sleeve"],
    },
    limit=3,
    allow_fallback=False,
)

print(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False,
    )
)