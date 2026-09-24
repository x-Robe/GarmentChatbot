import json

from src.product_search import ProductSearch


search = ProductSearch()

result = search.search(
    query="minimalist Japanese streetwear t-shirt",
    filters={},
    limit=5,
    allow_fallback=False,
)

print(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False,
    )
)