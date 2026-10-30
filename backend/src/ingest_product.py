import json
import os
from pathlib import Path
from qdrant_client import QdrantClient, models
from dotenv import load_dotenv

from asset_paths import resolve_catalog_path
from extract_embeding import FashionClipEmbedder
from qdrant_connection import FashionQdrantStore
from zero_shot_classifier import ZeroShotTshirtClassifier

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

def load_products(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as file:
        products = json.load(file)

    if not isinstance(products, list):
        raise ValueError("products.json must contain a JSON array.")

    return products


def validate_product(product: dict) -> Path:
    required_fields = [
        "id",
        "image_path",
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in product
    ]

    if missing_fields:
        raise ValueError(
            f"Product is missing fields: {missing_fields}"
        )

    image_path = Path(product["image_path"])

    if not image_path.is_absolute():
        image_path = resolve_catalog_path(image_path)

    image_path = image_path.resolve()

    if not image_path.is_file():
        raise FileNotFoundError(
            f"Image does not exist: {image_path}"
        )

    return image_path


def main() -> None:
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_api_key = os.environ.get("QDRANT_API")
    collection_name = os.environ.get("QDRANT_COLLECTION")

    products_file = Path(os.environ.get("PRODUCT_FILE"))
    if not products_file.is_absolute():
        products_file = PROJECT_ROOT / products_file

    batch_size = int(os.environ.get("BATCH_SIZE","32"))
    embedder = FashionClipEmbedder()

    classifier = ZeroShotTshirtClassifier(
        embed_texts=embedder.embed_texts,
    )

    store = FashionQdrantStore(
        url=qdrant_url,
        api_key=qdrant_api_key,
        collection_name=collection_name,
    )

    products = load_products(products_file)

    pending_points = []
    collection_initialized = False

    for index, product in enumerate(products, start=1):
        try:
            image_path = validate_product(product)

            print(
                f"[{index}/{len(products)}] "
                f"Processing {product['id']}"
            )

            image_embedding = embedder.embed_image(
                image_path,
            )

            if not collection_initialized:
                store.ensure_collection(
                    vector_size=len(image_embedding)
                )
                collection_initialized = True

            predicted_attributes = classifier.classify(
                image_embedding
            )

            payload = {
                "product_id": product["id"],
                "image_url": product["image_path"],

                # Trusted catalog data
                "category": product.get(
                    "category",
                    "t-shirt",
                ),
                # Zero-shot classifications
                "colors": predicted_attributes["colors"],
                "patterns": predicted_attributes["patterns"],
                "neckline": predicted_attributes["neckline"],
                "sleeve": predicted_attributes["sleeve"],
                "style": predicted_attributes["style"],
                "buttons": predicted_attributes["buttons"],

                # Useful for evaluation and model updates
                "classification_scores": (
                    predicted_attributes[
                        "classification_scores"
                    ]
                ),
                "embedding_model": (
                    "patrickjohncyh/fashion-clip"
                ),
                "classification_version": "tshirt-v1",
            }

            pending_points.append({
                "vector": image_embedding,
                "payload": payload,
            })

            if len(pending_points) >= batch_size:
                store.upsert_products(pending_points)
                pending_points.clear()

        except Exception as error:
            print(
                f"Failed to process "
                f"{product.get('id', 'unknown')}: "
                f"{error}"
            )

    if pending_points:
        store.upsert_products(pending_points)

    print("Ingestion completed.")


if __name__ == "__main__":
    main()