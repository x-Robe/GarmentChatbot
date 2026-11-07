"""Validated client-owned pagination state; no server memory or arbitrary filters."""
import json
from pathlib import Path
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

MAX_SHOWN_IDS = 4096
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "data/samples/sample_tshirt_schema.json").read_text())
RELATIONS = {"new_topic", "refinement", "more_results", "continuation",
             "fashion_information", "out_of_domain", "clarification", "image_refinement", "image_more_results"}

class ActiveSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_type: Literal["text", "image"]
    resolved_query: StrictStr = Field(default="", max_length=2000)
    mode: Literal["auto", "exact", "similar"] = "auto"
    search_strategy: Literal["exact", "similar", "both"] = "exact"
    attributes: dict = Field(default_factory=dict)
    shown_product_ids: list[StrictStr] = Field(default_factory=list, max_length=MAX_SHOWN_IDS)
    shown_point_ids: list[StrictStr] = Field(default_factory=list, max_length=MAX_SHOWN_IDS)

    @field_validator("shown_product_ids", "shown_point_ids", mode="before")
    @classmethod
    def identifiers(cls, value):
        if not isinstance(value, list) or len(value) > MAX_SHOWN_IDS:
            raise ValueError("Invalid identifier list")
        if any(isinstance(v, bool) or not isinstance(v, (str, int)) or not 1 <= len(str(v)) <= 128 for v in value):
            raise ValueError("Invalid identifier")
        return list(dict.fromkeys(str(v) for v in value))

    @field_validator("shown_point_ids")
    @classmethod
    def point_ids(cls, values):
        for value in values:
            if value.isdigit() and str(int(value)) == value and int(value) < 2**64:
                continue
            UUID(value)
        return values

    @field_validator("attributes")
    @classmethod
    def attributes_only(cls, values):
        if set(values) - set(SCHEMA):
            raise ValueError("Unsupported attribute key")
        for key, value in values.items():
            if key == "buttons":
                if not isinstance(value, bool): raise ValueError("Invalid buttons")
            elif isinstance(value, str):
                if value not in SCHEMA[key]: raise ValueError("Invalid attribute")
            elif isinstance(value, list):
                if len(value) > len(SCHEMA[key]) or any(not isinstance(v, str) or v not in SCHEMA[key] for v in value):
                    raise ValueError("Invalid attribute values")
            else:
                raise ValueError("Invalid attribute type")
        return values

    @model_validator(mode="after")
    def valid_search(self):
        if self.search_type == "text":
            if not self.resolved_query.strip(): raise ValueError("Missing search query")
            if self.mode != "auto" and self.mode != self.search_strategy:
                raise ValueError("Inconsistent mode and strategy")
        elif self.attributes or self.shown_product_ids or self.shown_point_ids or self.resolved_query:
            raise ValueError("Image state must not contain reference data")
        return self


def add_displayed(state, products):
    """Only the final response's displayed list counts, never raw candidates."""
    result = state.model_dump()
    for product in products:
        identifier = product.get("product_id")
        point = product.get("point_id")
        valid_point = False
        if point not in (None, ""):
            try:
                ActiveSearch.point_ids([str(point)])
                valid_point = True
            except (ValueError, TypeError):
                pass
        if identifier not in (None, ""):
            if str(identifier) not in result["shown_product_ids"]:
                result["shown_product_ids"].append(str(identifier))
        elif not valid_point:
            raise ValueError("Product has no stable pagination identity")
        if valid_point and str(point) not in result["shown_point_ids"]:
            result["shown_point_ids"].append(str(point))
    return type(state).model_validate(result).model_dump()
