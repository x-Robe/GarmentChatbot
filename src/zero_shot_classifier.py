# zero_shot_classifier.py

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np


ATTRIBUTE_LABELS = {
    "colors": [
        "black",
        "white",
        "gray",
        "red",
        "blue",
        "navy blue",
        "green",
        "yellow",
        "pink",
        "purple",
        "brown",
        "beige",
        "orange",
        "multicolor",
    ],
    "patterns": [
        "plain",
        "graphic print",
        "striped",
        "checked",
        "floral",
        "printed",
        "camouflage",
        "tie-dye",
        "polka dot",
        "logo print",
        "color block",
    ],
    "neckline": [
        "crew neck",
        "round neck",
        "v-neck",
        "scoop neck",
        "polo collar",
        "henley neck",
        "mock neck",
        "turtleneck",
    ],
    "sleeve": [
        "sleeveless",
        "cap sleeve",
        "short sleeve",
        "three-quarter sleeve",
        "long sleeve",
    ],
    "style": [
        "casual",
        "streetwear",
        "sportswear",
        "smart casual",
        "vintage",
        "minimalist",
        "oversized",
        "regular fit",
        "slim fit",
        "athletic fit",
    ],
    "buttons": [
        "with visible buttons",
        "without visible buttons",
    ],
}


PROMPT_TEMPLATES = {
    "colors": "a product photo of a {label} t-shirt",
    "patterns": "a product photo of a t-shirt with a {label} pattern",
    "neckline": "a product photo of a t-shirt with a {label}",
    "sleeve": "a product photo of a t-shirt with {label}",
    "style": "a product photo of a {label} t-shirt",
    "buttons": "a product photo of a t-shirt {label}",
}


@dataclass
class Prediction:
    label: str
    score: float


class ZeroShotTshirtClassifier:
    """
    Classify a FashionCLIP image embedding by comparing it with
    FashionCLIP text embeddings.
    """

    def __init__(
        self,
        embed_texts: Callable[[Sequence[str]], np.ndarray],
    ):
        self.embed_texts = embed_texts
        self.label_embeddings: dict[str, np.ndarray] = {}

        self._prepare_label_embeddings()

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(vector)

        if norm < 1e-12:
            raise ValueError("Received an empty or zero image embedding.")

        return vector / norm

    def _prepare_label_embeddings(self) -> None:
        """
        Precompute label embeddings once when the classifier starts.
        """

        for attribute, labels in ATTRIBUTE_LABELS.items():
            template = PROMPT_TEMPLATES[attribute]

            prompts = [
                template.format(label=label)
                for label in labels
            ]

            embeddings = self.embed_texts(prompts)
            self.label_embeddings[attribute] = embeddings

    def _rank(
        self,
        image_embedding: np.ndarray,
        attribute: str,
    ) -> list[Prediction]:
        image_embedding = self._normalize(image_embedding)

        text_embeddings = self.label_embeddings[attribute]
        labels = ATTRIBUTE_LABELS[attribute]

        # Dot product equals cosine similarity because vectors
        # have been normalized.
        scores = text_embeddings @ image_embedding

        sorted_indices = np.argsort(scores)[::-1]

        return [
            Prediction(
                label=labels[index],
                score=float(scores[index]),
            )
            for index in sorted_indices
        ]

    def classify_single(
        self,
        image_embedding: np.ndarray,
        attribute: str,
    ) -> Prediction:
        return self._rank(
            image_embedding=image_embedding,
            attribute=attribute,
        )[0]

    def classify_multiple(
        self,
        image_embedding: np.ndarray,
        attribute: str,
        max_labels: int = 2,
        similarity_margin: float = 0.03,
    ) -> list[Prediction]:
        """
        Select the best label and any additional labels sufficiently
        close to the best score.

        similarity_margin is a heuristic that must be validated against
        your own labeled dataset.
        """

        predictions = self._rank(
            image_embedding=image_embedding,
            attribute=attribute,
        )

        best_score = predictions[0].score

        selected = [
            prediction
            for prediction in predictions[:max_labels]
            if prediction.score >= best_score - similarity_margin
        ]

        return selected

    def classify(
        self,
        image_embedding: np.ndarray,
    ) -> dict:
        color_predictions = self.classify_multiple(
            image_embedding=image_embedding,
            attribute="colors",
            max_labels=2,
            similarity_margin=0.025,
        )

        pattern_predictions = self.classify_multiple(
            image_embedding=image_embedding,
            attribute="patterns",
            max_labels=2,
            similarity_margin=0.02,
        )

        style_predictions = self.classify_multiple(
            image_embedding=image_embedding,
            attribute="style",
            max_labels=2,
            similarity_margin=0.025,
        )

        neckline = self.classify_single(
            image_embedding,
            "neckline",
        )

        sleeve = self.classify_single(
            image_embedding,
            "sleeve",
        )

        buttons = self.classify_single(
            image_embedding,
            "buttons",
        )

        return {
            "colors": [
                prediction.label
                for prediction in color_predictions
            ],
            "patterns": [
                prediction.label
                for prediction in pattern_predictions
            ],
            "neckline": neckline.label,
            "sleeve": sleeve.label,
            "style": [
                prediction.label
                for prediction in style_predictions
            ],
            "buttons": buttons.label == "with visible buttons",

            # Keep scores for evaluation and debugging.
            "classification_scores": {
                "colors": {
                    prediction.label: prediction.score
                    for prediction in color_predictions
                },
                "patterns": {
                    prediction.label: prediction.score
                    for prediction in pattern_predictions
                },
                "neckline": neckline.score,
                "sleeve": sleeve.score,
                "style": {
                    prediction.label: prediction.score
                    for prediction in style_predictions
                },
                "buttons": buttons.score,
            },
        }