from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from PIL import Image
import os
from dotenv import load_dotenv
from transformers import AutoModel, AutoProcessor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

class FashionClipEmbedder:
    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = torch.device(device)
        self.model_name = os.getenv("CLIP_MODEL")

        self.processor = AutoProcessor.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)

        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def normalize(embeddings: np.ndarray) -> np.ndarray:
        embeddings = np.asarray(embeddings, dtype=np.float32)

        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)

        norms = np.linalg.norm(
            embeddings,
            axis=1,
            keepdims=True,
        )

        norms = np.clip(norms, a_min=1e-12, a_max=None)
        return embeddings / norms

    @staticmethod
    def _extract_embedding(output) -> torch.Tensor:
        """
        Extract projected embeddings across Transformers versions.
        """
        if isinstance(output, torch.Tensor):
            return output

        if hasattr(output, "text_embeds"):
            embedding = output.text_embeds
            if embedding is not None:
                return embedding

        if hasattr(output, "image_embeds"):
            embedding = output.image_embeds
            if embedding is not None:
                return embedding

        if hasattr(output, "pooler_output"):
            embedding = output.pooler_output
            if embedding is not None:
                return embedding

        if isinstance(output, (tuple, list)) and output:
            if isinstance(output[0], torch.Tensor):
                return output[0]

        raise TypeError(
            "Could not extract an embedding tensor from "
            f"{type(output).__name__}"
        )

    @torch.inference_mode()
    def embed_image(
            self,
            image_path: str | Path,
    ) -> np.ndarray:
        image_path = Path(image_path)

        with Image.open(image_path) as image:
            image = image.convert("RGB")

            inputs = self.processor(
                images=image,
                return_tensors="pt",
            )

        inputs = {
            key: value.to(self.device)
            for key, value in inputs.items()
        }

        model_output = self.model.get_image_features(
            **inputs
        )

        embedding = self._extract_embedding(
            model_output
        )

        embedding = (
            embedding.detach()
            .cpu()
            .float()
            .numpy()
        )

        embedding = self.normalize(embedding)

        return embedding[0]

    @torch.inference_mode()
    def embed_texts(
            self,
            texts: Sequence[str],
    ) -> np.ndarray:
        if not texts:
            return np.empty(
                (0, self.model.config.projection_dim),
                dtype=np.float32,
            )

        inputs = self.processor(
            text=list(texts),
            padding=True,
            truncation=True,
            return_tensors="pt",
        )

        inputs = {
            key: value.to(self.device)
            for key, value in inputs.items()
        }

        model_output = self.model.get_text_features(
            **inputs
        )

        embeddings = self._extract_embedding(
            model_output
        )

        embeddings = (
            embeddings.detach()
            .cpu()
            .float()
            .numpy()
        )

        return self.normalize(embeddings)