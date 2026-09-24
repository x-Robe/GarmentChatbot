from src.product_search import QueryAttributeExtractor


extractor = QueryAttributeExtractor()

queries = [
    "navy blue striped crew neck t-shirt",
    "black oversized graphic shirt",
    "white short-sleeve shirt with visible buttons",
]

for query in queries:
    print("=" * 60)
    print("Query:", query)
    print("Attributes:", extractor.extract(query))