import json
import os
from pathlib import Path
from typing import Any

import openai



PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SCHEMA_PATH = (
    PROJECT_ROOT
    / "data"
    / "samples"
    / "sample_tshirt_schema.json"
)


class QueryAttributeExtractor:
    def __init__(
        self,
        schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    ) -> None:
        self.client = openai.OpenAI(
            api_key=os.getenv("POE_API"),
            base_url=os.getenv("POE_URL"),
        )

        self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()
        self.output_schema = self._build_strict_schema()

    def _load_schema(self) -> dict[str, Any]:
        if not self.schema_path.exists():
            raise FileNotFoundError(
                f"Attribute schema was not found: "
                f"{self.schema_path}"
            )

        with self.schema_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            document = json.load(file)

        return document

    def _nullable_enum(
        self,
        values: list[str],
    ) -> dict[str, Any]:
        return {
            "type": ["string", "null"],
            "enum": [*values, None],
        }

    def _enum_array(
        self,
        values: list[str],
    ) -> dict[str, Any]:
        return {
            "type": "array",
            "items": {
                "type": "string",
                "enum": values,
            },
            "uniqueItems": True,
        }

    def _build_strict_schema(self) -> dict[str, Any]:
        document = self.schema

        schema = {
            "type": "object",
            "properties": {
                "category": self._nullable_enum(
                    document["category"]
                ),
                "colors": self._enum_array(
                    document["colors"]
                ),
                "patterns": self._enum_array(
                    document["patterns"]
                ),
                "neckline": self._nullable_enum(
                    document["neckline"]
                ),
                "sleeve": self._nullable_enum(
                    document["sleeve"]
                ),
                "style": self._enum_array(
                    document["style"]
                ),
                "buttons": {
                    "type": ["boolean", "null"],
                },
                "search_text": {
                    "type": "string",
                    "description": (
                        "A concise visual product description "
                        "for semantic or vector search."
                    ),
                },
            },
            "required": [
                "category",
                "colors",
                "patterns",
                "neckline",
                "sleeve",
                "style",
                "buttons",
                "search_text",
            ],
            "additionalProperties": False,
        }

        return schema

    def extract(
            self,
            query: str,
    ) -> dict[str, Any]:
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "Extract product-search attributes from the "
                "customer's request.\n"
                "\n"
                "Rules:\n"
                "- Only select values allowed by the schema.\n"
                "- Do not invent unspecified preferences.\n"
                "- Use null for unspecified singular values.\n"
                "- Use empty arrays for unspecified multi-value "
                "attributes.\n"
                "- Set buttons to null when the customer does "
                "not mention buttons.\n"
                "- Preserve important visual details in "
                "search_text."
            ),
            input=query,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "tshirt_query_attributes",
                    "schema": self.output_schema,
                    "strict": True,
                }
            },
            store=False,
        )

        return json.loads(response.output_text)