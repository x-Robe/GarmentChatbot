from src.product_search import ProductSearch


search = ProductSearch()

collection = search.client.get_collection(
    collection_name=search.collection_name,
)

print("Connected to Qdrant")
print("Collection:", search.collection_name)
print(collection)