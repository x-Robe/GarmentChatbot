import os
import re
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from .extract_embeding import FashionClipEmbedder
from .zero_shot_classifier import (
    ATTRIBUTE_LABELS,
    PROMPT_TEMPLATES,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class QueryAttributeExtractor:
    """
    Map a natural-language user query to the labels used in
    the Qdrant payload.

    Sentence Transformer is used for semantic label matching.
    """

    def __init__(
        self,
        model_name: str = (
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
    ):
        self.model = SentenceTransformer(model_name)

        self.label_embeddings: dict[str, np.ndarray] = {}

        for attribute, labels in ATTRIBUTE_LABELS.items():
            template = PROMPT_TEMPLATES[attribute]

            label_prompts = [
                template.format(label=label)
                for label in labels
            ]

            embeddings = self.model.encode(
                label_prompts,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            self.label_embeddings[attribute] = embeddings

    @staticmethod
    def _find_exact_labels(
        query: str,
        labels: list[str],
    ) -> list[str]:
        """
        Find labels explicitly mentioned in the query.
        """

        query = query.lower()
        matches = []

        # Check longer labels first so "navy blue" takes
        # priority over "blue".
        sorted_labels = sorted(
            labels,
            key=len,
            reverse=True,
        )

        for label in sorted_labels:
            pattern = rf"\b{re.escape(label.lower())}\b"

            if re.search(pattern, query):
                # Avoid returning both "navy blue" and "blue".
                if not any(
                    label in existing
                    or existing in label
                    for existing in matches
                ):
                    matches.append(label)

        return matches

    def extract(
        self,
        query: str,
    ) -> dict[str, list[str]]:
        query_embedding = self.model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        extracted: dict[str, list[str]] = {}

        thresholds = {
            "colors": 0.40,
            "patterns": 0.40,
            "neckline": 0.42,
            "sleeve": 0.42,
            "style": 0.40,
            "buttons": 0.43,
        }

        multi_value_attributes = {
            "colors",
            "patterns",
            "style",
        }

        for attribute, labels in ATTRIBUTE_LABELS.items():
            exact_matches = self._find_exact_labels(
                query,
                labels,
            )

            if exact_matches:
                if attribute in multi_value_attributes:
                    extracted[attribute] = exact_matches[:2]
                else:
                    extracted[attribute] = exact_matches[:1]

                continue

            label_embeddings = self.label_embeddings[attribute]

            similarities = (
                label_embeddings @ query_embedding
            )

            sorted_indices = np.argsort(
                similarities
            )[::-1]

            best_index = int(sorted_indices[0])
            best_score = float(similarities[best_index])

            second_score = (
                float(similarities[sorted_indices[1]])
                if len(sorted_indices) > 1
                else -1.0
            )

            # Only use semantic extraction when the match is
            # sufficiently strong and separated from second place.
            if (
                best_score >= thresholds[attribute]
                and best_score - second_score >= 0.02
            ):
                extracted[attribute] = [
                    labels[best_index]
                ]

        return extracted


class ProductSearch:
    def __init__(self):
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API") or None
        collection_name = os.getenv(
            "QDRANT_COLLECTION"
        )

        if not qdrant_url:
            raise RuntimeError(
                "QDRANT_URL is missing."
            )

        if not collection_name:
            raise RuntimeError(
                "QDRANT_COLLECTION is missing."
            )

        self.collection_name = collection_name

        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
        )

        # Must be the same model used during ingestion.
        self.embedder = FashionClipEmbedder()

        # Used only for attribute/keyword extraction.
        self.attribute_extractor = (
            QueryAttributeExtractor()
        )

    @staticmethod
    def _build_filter(
            attributes: dict[str, Any],
    ) -> models.Filter | None:
        conditions = []

        for attribute, value in attributes.items():
            if attribute == "search_text":
                continue

            if value is None:
                continue

            if isinstance(value, (list, dict, str)) and not value:
                continue

            if attribute == "buttons":
                # Support the LLM extractor's Boolean format.
                if isinstance(value, bool):
                    has_buttons = value

                # Also support the older local extractor's list format.
                elif isinstance(value, list) and value:
                    has_buttons = (
                            value[0] == "with visible buttons"
                    )

                else:
                    continue

                conditions.append(
                    models.FieldCondition(
                        key="buttons",
                        match=models.MatchValue(
                            value=has_buttons,
                        ),
                    )
                )

                continue

            # MatchAny requires a list of possible values.
            values = value if isinstance(value, list) else [value]

            conditions.append(
                models.FieldCondition(
                    key=attribute,
                    match=models.MatchAny(
                        any=values,
                    ),
                )
            )

        if not conditions:
            return None

        return models.Filter(
            must=conditions,
        )

    @staticmethod
    def _label_matches(
            payload: dict[str, Any],
            extracted: dict[str, Any],
    ) -> dict[str, bool]:
        matches: dict[str, bool] = {}

        for attribute, expected in extracted.items():
            if attribute == "search_text":
                continue

            if expected is None:
                continue

            if isinstance(expected, (list, str)) and not expected:
                continue

            stored = payload.get(attribute)

            if attribute == "buttons":
                if isinstance(expected, bool):
                    expected_boolean = expected

                elif isinstance(expected, list) and expected:
                    expected_boolean = (
                            expected[0]
                            == "with visible buttons"
                    )

                else:
                    continue

                matches[attribute] = (
                        stored == expected_boolean
                )

                continue

            expected_values = (
                expected
                if isinstance(expected, list)
                else [expected]
            )

            stored_values = (
                stored
                if isinstance(stored, list)
                else [stored]
            )

            matches[attribute] = any(
                value in stored_values
                for value in expected_values
            )

        return matches

    def _query_qdrant(
        self,
        query_vector: np.ndarray,
        query_filter: models.Filter | None,
        limit: int,
    ):
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        return response.points

    def search(
            self,
            query: str,
            filters: dict[str, Any] | None = None,
            limit: int = 5,
            allow_fallback: bool = True,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValueError(
                "Search query cannot be empty."
            )

        if not 1 <= limit <= 20:
            raise ValueError(
                "Limit must be between 1 and 20."
            )

        search_prompt = (
            f"a product photo of a t-shirt matching: {query}"
        )

        query_vector = self.embedder.embed_texts(
            [search_prompt]
        )[0]

        # Use filters supplied by the caller. If no filters were
        # supplied, extract them from the user's query.
        if filters is None:
            extracted_attributes = (
                self.attribute_extractor.extract(query)
            )
        else:
            extracted_attributes = filters

        query_filter = self._build_filter(
            extracted_attributes
        )

        points = self._query_qdrant(
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        # Only broaden the search when explicitly allowed.
        if (
                allow_fallback
                and len(points) < limit
                and query_filter is not None
        ):
            fallback_points = self._query_qdrant(
                query_vector=query_vector,
                query_filter=None,
                limit=limit * 3,
            )

            existing_ids = {
                str(point.id)
                for point in points
            }

            for point in fallback_points:
                point_id = str(point.id)

                if point_id in existing_ids:
                    continue

                points.append(point)
                existing_ids.add(point_id)

                if len(points) >= limit:
                    break

        results = []

        for point in points[:limit]:
            payload = point.payload or {}

            results.append({
                "point_id": str(point.id),
                "product_id": payload.get("product_id"),
                "similarity_score": round(
                    float(point.score),
                    4,
                ),
                "image_path": payload.get("image_url"),
                "attributes": {
                    "category": payload.get("category"),
                    "colors": payload.get("colors", []),
                    "patterns": payload.get(
                        "patterns",
                        [],
                    ),
                    "neckline": payload.get("neckline"),
                    "sleeve": payload.get("sleeve"),
                    "style": payload.get("style", []),
                    "buttons": payload.get("buttons"),
                },
                "label_matches": self._label_matches(
                    payload,
                    extracted_attributes,
                ),
            })

        return {
            "query": query,
            "extracted_attributes": extracted_attributes,
            "result_count": len(results),
            "results": results,
        }