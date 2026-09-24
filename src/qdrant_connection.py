import uuid
from typing import Any, Sequence

import numpy as np
from qdrant_client import QdrantClient, models


class FashionQdrantStore:
    def __init__(
        self,
        url: str,
        collection_name: str,
        api_key: str | None = None,
    ):
        self.collection_name = collection_name

        self.client = QdrantClient(
            url=url,
            api_key=api_key,
        )

    def ensure_collection(
        self,
        vector_size: int,
    ) -> None:
        if self.client.collection_exists(self.collection_name):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

        self._create_payload_indexes()

    def _create_payload_indexes(self) -> None:
        keyword_fields = [
            "product_id",
            "category",
            "colors",
            "patterns",
            "neckline",
            "sleeve",
            "size",
            "style",
        ]

        for field_name in keyword_fields:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name="buttons",
            field_schema=models.PayloadSchemaType.BOOL,
            wait=True,
        )

    @staticmethod
    def create_point_id(
        product_id: str,
        image_url: str,
    ) -> str:
        """
        Generate a stable UUID because Qdrant point IDs must be
        unsigned integers or UUID strings.
        """

        source = f"{product_id}:{image_url}"

        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                source,
            )
        )

    def upsert_product(
        self,
        vector: np.ndarray,
        payload: dict[str, Any],
    ) -> str:
        vector = np.asarray(
            vector,
            dtype=np.float32,
        ).reshape(-1)

        point_id = self.create_point_id(
            product_id=payload["product_id"],
            image_url=payload["image_url"],
        )

        point = models.PointStruct(
            id=point_id,
            vector=vector.tolist(),
            payload=payload,
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
            wait=True,
        )

        return point_id

    def upsert_products(
        self,
        points: Sequence[dict],
    ) -> None:
        qdrant_points = []

        for item in points:
            payload = item["payload"]

            point_id = self.create_point_id(
                product_id=payload["product_id"],
                image_url=payload["image_url"],
            )

            vector = np.asarray(
                item["vector"],
                dtype=np.float32,
            ).reshape(-1)

            qdrant_points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload=payload,
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=qdrant_points,
            wait=True,
        )