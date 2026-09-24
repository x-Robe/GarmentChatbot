from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoProcessor, CLIPModel

from qdrant_client import QdrantClient

import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

class FashionCLIP():
    """
    Handles all FashionCLIP model operations.

    Responsibilities:
    - Device selection
    - Model and processor loading
    - Image loading and preprocessing
    - Image embedding generation
    - Text embedding generation
    - Vector normalization
    - Similarity calculation
    - Local text-to-image search
    """
    def __init__(self, model_name: str |None=None, device: str |None=None)->None:
        self.model_name = os.getenv("CLIP_MODEL")
        self.device = device
        print(f"Loading FashionCLIP: {self.model_name}")
        print(f"Device: {self.device}")

        self.processor = AutoProcessor.from_pretrained(
            self.model_name
        )

        self.model = CLIPModel.from_pretrained(
            self.model_name
        )

        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def get_device() -> str:
        if torch.cuda.is_available():
            return "cuda"

        if (
                hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()
        ):
            return "mps"

        return "cpu"

    def load_data(image_path: Path):
        """
        Load an image and convert it to RGB.
        """
        with Image.open(image_path) as image:
            return image.convert("RGB")

    @property
    def embedding_dimension(self) -> int:
        """
        Return the model's embedding dimension.
        """
        return int(self.model.config.projection_dim)

    def _extract_tensor(model_output) -> torch.Tensor:
        """
        Extract a tensor from different Transformers output formats.
        """
        if isinstance(model_output, torch.Tensor):
            return model_output

        if hasattr(model_output, "image_embeds"):
            return model_output.image_embeds

        if hasattr(model_output, "text_embeds"):
            return model_output.text_embeds

        if hasattr(model_output, "pooler_output"):
            return model_output.pooler_output

        if isinstance(model_output, (tuple, list)):
            return model_output[0]

        raise TypeError(
            "Unable to extract an embedding tensor from "
            f"output type: {type(model_output)}")

    def normalize(embeddings: torch.Tensor,) -> torch.Tensor:
            """
            L2-normalize embeddings.
            After normalization, dot product is equivalent to
            cosine similarity.
            """
            return F.normalize(
                embeddings.float(),
                p=2,
                dim=-1,
            )

    @torch.inference_mode()
    def encode_data(self,images: Sequence[Image.Image],normalize=True)->np.ndarray:
        """
        Generate embeddings for a sequence of PIL images.

        Returns:
            NumPy array with shape:
            (number_of_images, embedding_dimension)
        """
        if not images:
            return np.empty(
                (0, self.embedding_dimension),
                dtype=np.float32,
            )

        inputs = self.processor(
            images=list(images),
            return_tensors="pt",
        )

        pixel_values = inputs["pixel_values"].to(
            self.device
        )

        model_output = self.model.get_image_features(
            pixel_values=pixel_values
        )

        embeddings = self._extract_tensor(model_output)

        if normalize:
            embeddings = self.normalize(embeddings)
        else:
            embeddings = embeddings.float()

        return embeddings.cpu().numpy().astype(
            np.float32
        )
    def encode_image_paths(
        self,
        image_paths: Sequence[str | Path],
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Load images from disk and generate embeddings.
        """

        images = [
            self.load_image(image_path)
            for image_path in image_paths
        ]

        return self.encode_images(
            images=images,
            normalize=normalize,
        )

    @torch.inference_mode()
    def encode_texts(
        self,
        texts: Sequence[str],
        normalize: bool = True,
    ) -> np.ndarray:
        """
        Generate embeddings for one or more text queries.

        Returns:
            NumPy array with shape:
            (number_of_texts, embedding_dimension)
        """

        if not texts:
            return np.empty(
                (0, self.embedding_dimension),
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

        embeddings = self._extract_tensor(model_output)

        if normalize:
            embeddings = self.normalize(embeddings)
        else:
            embeddings = embeddings.float()

        return embeddings.cpu().numpy().astype(
            np.float32
        )