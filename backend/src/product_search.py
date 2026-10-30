from .asset_paths import resolve_catalog_path
from .result_count import DEFAULT_RESULT_COUNT, MIN_RESULT_COUNT, MAX_RESULT_COUNT
import os
import logging
import re
from pathlib import Path
from typing import Any

from PIL import Image

import numpy as np
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from .extract_embeding import FashionClipEmbedder
from .hybrid_image_search import retrieve_hybrid, reliable_image_attributes, image_strategy, MAX_HARD_FILTERS
from .zero_shot_classifier import (
    ATTRIBUTE_LABELS,
    ZeroShotTshirtClassifier,
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

    @staticmethod
    def _exclude_shown(query_filter, excluded):
        if not excluded:
            return query_filter
        query_filter = query_filter.model_copy(deep=True) if query_filter is not None else models.Filter()
        conditions = list(query_filter.must_not or [])
        identifiers = excluded.get("shown_product_ids", [])
        if identifiers:
            conditions.append(models.FieldCondition(key="product_id", match=models.MatchAny(any=identifiers)))
            # Payload IDs are integers in this catalog; also cover legacy string IDs.
            numbers = [int(v) for v in identifiers if v.lstrip("-").isdigit()
                       and str(int(v)) == v and -(2**63) <= int(v) < 2**63]
            if numbers:
                conditions.append(models.FieldCondition(key="product_id", match=models.MatchAny(any=numbers)))
        points = excluded.get("shown_point_ids", [])
        if points:
            conditions.append(models.HasIdCondition(has_id=[int(v) if v.isdigit() else v for v in points]))
        query_filter.must_not = conditions
        return query_filter

    def _query_text_page(self, vector, positive_filter, limit, excluded):
        """Prefer product-level must_not. Some hosted collections reject it when
        numeric payload IDs have only a keyword index. Do not alter indexes:
        exclude known point IDs server-side and adaptively examine ranked points,
        rejecting every representation of already shown products locally.
        """
        if not excluded:
            return self._query_qdrant(query_vector=vector, query_filter=positive_filter, limit=limit)
        if not getattr(self, "_product_exclusion_fallback", False):
            try:
                return self._query_qdrant(query_vector=vector, query_filter=self._exclude_shown(positive_filter, excluded), limit=limit)
            except Exception as exc:
                # Only this known index limitation permits fallback; outages propagate.
                content = getattr(exc, "content", b"")
                if isinstance(content, bytes): content = content.decode("utf-8", errors="replace")
                if (getattr(exc, "status_code", None) != 400 or
                        "index" not in content.lower() or "product_id" not in content):
                    raise
                self._product_exclusion_fallback = True
                logging.getLogger(__name__).info("Product-ID index incompatible; using bounded adaptive pagination")
        fallback_filter = self._exclude_shown(positive_filter,
            {"shown_point_ids": excluded.get("shown_point_ids", [])})
        seen = set(excluded.get("shown_product_ids", []))
        budget = limit
        while True:
            points = self._query_qdrant(query_vector=vector, query_filter=fallback_filter, limit=budget)
            unseen = [p for p in points if str((p.payload or {}).get("product_id")) not in seen]
            if len(unseen) >= limit:
                return unseen[:limit]
            if len(points) < budget:
                return unseen
            if budget >= 4096:
                raise RuntimeError("Pagination scan budget reached; refine search")
            budget = min(4096, budget * 2)

    def search(
            self,
            query: str,
            filters: dict[str, Any] | None = None,
            limit: int = 5,
            allow_fallback: bool = True,
            excluded: dict | None = None,
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

        query_filter = self._build_filter(extracted_attributes)

        points = self._query_text_page(query_vector, query_filter, limit, excluded)

        # Only broaden the search when explicitly allowed.
        if (
                allow_fallback
                and len(points) < limit
                and query_filter is not None
        ):
            fallback_points = self._query_qdrant(
                query_vector=query_vector,
                query_filter=self._exclude_shown(None, excluded),
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

        results = self._format_results(points[:limit], extracted_attributes)

        return {
            "query": query,
            "extracted_attributes": extracted_attributes,
            "result_count": len(results),
            "results": results,
        }

    def _format_results(self, points, attributes):
        """Shared payload projection; preserves Qdrant order and existing fields."""
        results = []

        for point in points:
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
                    attributes,
                ),
            })

        return results

    def search_by_image_path(self, image_path: str | Path, limit: int = DEFAULT_RESULT_COUNT) -> dict[str, Any]:
        """Pure image retrieval using the ingestion encoder; no LLM or filters.

        Catalog paths resolve from the repository root, as in ingestion. No text
        quality cutoff, self exclusion, reranking or new model is introduced.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("Limit must be an integer between 1 and 20.")
        path = Path(image_path)
        if not path.is_absolute():
            path = resolve_catalog_path(path)
        if not path.is_file():
            raise FileNotFoundError("Query image does not exist or is not a file.")
        try:
            image = Image.open(path)
            try:
                image.load()
            except Exception:
                image.close()
                raise
        except OSError:
            raise ValueError("Query image could not be decoded as a supported image.") from None
        with image:
            result = self.search_by_image(image, limit=limit)
        return {"query_image": str(image_path), **result}

    def search_by_image(self, image: Image.Image, limit: int = DEFAULT_RESULT_COUNT) -> dict[str, Any]:
        """In-memory image retrieval; uses the shared ingestion encoder."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("Limit must be an integer between 1 and 20.")
        vector = self.embedder.embed_pil_image(image)
        return self.search_by_image_vector_only(vector, limit)

    def search_by_image_vector_only(self, vector: np.ndarray, limit: int = DEFAULT_RESULT_COUNT) -> dict:
        """Original pure visual baseline, also usable with an already encoded image."""
        points = self._query_qdrant(query_vector=vector, query_filter=None, limit=limit)
        results = self._format_results(points[:limit], {})
        return {"embedding_dimension": int(vector.shape[0]),
                "result_count": len(results), "results": results}


    def search_by_image_hybrid(self, image: Image.Image, limit: int = DEFAULT_RESULT_COUNT,
                               include_diagnostics: bool = False, mode: str = 'auto') -> dict:
        if isinstance(limit, bool) or not isinstance(limit, int) or not MIN_RESULT_COUNT <= limit <= MAX_RESULT_COUNT:
            raise ValueError(f"Limit must be an integer between {MIN_RESULT_COUNT} and {MAX_RESULT_COUNT}.")
        vector = self.embedder.embed_pil_image(image)  # Exactly one image encoding.
        return self.search_by_image_vector_hybrid(vector, limit, include_diagnostics, mode=mode)

    def search_by_image_vector_hybrid(self, vector: np.ndarray, limit: int = DEFAULT_RESULT_COUNT,
                                      include_diagnostics: bool = False, mode: str = 'auto') -> dict:
        if isinstance(limit, bool) or not isinstance(limit, int) or not MIN_RESULT_COUNT <= limit <= MAX_RESULT_COUNT:
            raise ValueError(f"Limit must be an integer between {MIN_RESULT_COUNT} and {MAX_RESULT_COUNT}.")
        try:
            if getattr(self, "_image_classifier", None) is None:
                self._image_classifier = ZeroShotTshirtClassifier(self.embedder.embed_texts)
            attributes = self._image_classifier.analyze(vector)
        except Exception as exc:
            if mode != "auto":
                return self.search_by_image_embedding(vector, {}, limit=limit, mode=mode)
            result = self.search_by_image_vector_only(vector, limit)
            result.update(requested_mode="auto", effective_mode="auto", effective_image_strategy="pure_image_similarity")
            result["image_analysis"] = {"attributes": {}, "filters_used": {}, "strategy": "pure_visual"}
            if include_diagnostics:
                result["diagnostics"] = {"analysis_error_type": type(exc).__name__,
                                         "final_result_count": result["result_count"]}
            return self._reference_result(result, vector, {})
        return self.search_by_image_embedding(vector, attributes, limit=limit,
                                              include_diagnostics=include_diagnostics, mode=mode)

    def _reference_result(self, result, vector, attributes):
        result["image_reference"] = {"version": 1, "model": self.embedder.model_name,
            "dimension": int(vector.shape[0]), "embedding": vector.tolist(),
            "image_analysis": attributes}
        return result

    def search_by_image_embedding(self, vector, attributes, overrides=None, limit=DEFAULT_RESULT_COUNT,
                                  excluded=None, effective_filters=None, include_diagnostics=False, mode="auto",
                                  effective_image_strategy=None):
        """Reuse original analysis and vector. Pagination freezes effective filters."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not MIN_RESULT_COUNT <= limit <= MAX_RESULT_COUNT:
            raise ValueError("Invalid limit")
        if mode not in {"auto", "exact", "similar"}:
            raise ValueError("Invalid image search mode")
        overrides = dict(overrides or {})
        if effective_filters is not None and any(effective_filters.get(k) != v for k, v in overrides.items()):
            raise ValueError("Explicit requirements must remain mandatory")
        if effective_filters is not None and mode == "similar" and effective_filters != overrides:
            raise ValueError("Similar cannot use image-inferred filters")
        if effective_filters is None and mode != "auto":
            effective_filters = dict(overrides)
            if mode == "exact":
                for key, prediction in reliable_image_attributes(attributes, overrides)[:MAX_HARD_FILTERS]:
                    effective_filters[key] = prediction['label'] == 'with visible buttons' if key == 'buttons' else prediction['label']
        if effective_filters is not None:
            actual_strategy = image_strategy(mode, effective_filters, overrides)
            if effective_image_strategy is not None and effective_image_strategy != actual_strategy:
                raise ValueError("Inconsistent image strategy")
            points = [] if actual_strategy == "attributes_required" else self._query_text_page(vector, self._build_filter(effective_filters), limit, excluded)
            analysis = {"attributes": {key: {**value, "used_for_filter": key in effective_filters and key not in overrides}
                                       for key, value in attributes.items()},
                        "filters_used": effective_filters,
                        "strategy": actual_strategy if mode != "auto" else ("image_with_attribute_override" if overrides else
                                    ("attribute_guided_visual" if effective_filters else "pure_visual"))}
            diagnostics = {}
        else:
            points, analysis, diagnostics = retrieve_hybrid(
                vector, attributes, limit,
                lambda filter_: self.client.count(collection_name=self.collection_name,
                    count_filter=filter_, exact=True).count,
                lambda vector_, filter_, limit_: self._query_qdrant(
                    query_vector=vector_, query_filter=filter_, limit=limit_),
                self._build_filter, mandatory=overrides)
        results = self._format_results(points[:limit], analysis["filters_used"])
        resolved = {key: (value["label"] == "with visible buttons" if key == "buttons"
                         else [value["label"]]) for key,value in attributes.items()}
        resolved.update(overrides)
        result = {"embedding_dimension": int(vector.shape[0]), "result_count": len(results),
                  "results": results, "image_analysis": analysis, "resolved_attributes": resolved,
                  "requested_mode": mode, "effective_mode": mode,
                  "effective_image_strategy": image_strategy(mode, analysis["filters_used"], overrides)}
        if include_diagnostics: result["diagnostics"] = diagnostics
        return self._reference_result(result, vector, attributes)

    def search_by_image_with_overrides(self, image: Image.Image, overrides: dict,
                                       limit: int = DEFAULT_RESULT_COUNT, mode: str = "auto") -> dict:
        if isinstance(limit, bool) or not isinstance(limit, int) or not MIN_RESULT_COUNT <= limit <= MAX_RESULT_COUNT:
            raise ValueError(f"Limit must be an integer between {MIN_RESULT_COUNT} and {MAX_RESULT_COUNT}.")
        if not overrides: raise ValueError("Explicit overrides required")
        vector = self.embedder.embed_pil_image(image)
        try:
            if getattr(self, "_image_classifier", None) is None:
                self._image_classifier = ZeroShotTshirtClassifier(self.embedder.embed_texts)
            attributes = self._image_classifier.analyze(vector)
        except Exception:
            attributes = {}
        return self.search_by_image_embedding(vector, attributes, overrides, limit, mode=mode)
