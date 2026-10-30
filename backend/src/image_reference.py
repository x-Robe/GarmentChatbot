"""Client-owned image context. Never pass this object to a language model."""
import math
import os
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator
from .zero_shot_classifier import ATTRIBUTE_LABELS
from .search_state import ActiveSearch


def validate_overrides(values):
    if not isinstance(values, dict) or set(values) - set(ATTRIBUTE_LABELS):
        raise ValueError('Invalid image attributes')
    for key, value in values.items():
        if key == 'buttons':
            if type(value) is not bool: raise ValueError('Invalid buttons')
        elif (not isinstance(value, list) or not value or len(value) > len(ATTRIBUTE_LABELS[key])
              or any(not isinstance(v, str) or v not in ATTRIBUTE_LABELS[key] for v in value)):
            raise ValueError('Invalid attribute values')
    return values


class ImageReference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: Literal[1]
    model: StrictStr = Field(max_length=200)
    dimension: Literal[512]
    embedding: list[float] = Field(min_length=512, max_length=512)
    image_analysis: dict

    @field_validator('version', 'dimension', mode='before')
    @classmethod
    def integer_metadata(cls, value):
        if type(value) is not int:
            raise ValueError('Invalid reference version or dimension')
        return value

    @field_validator('embedding', mode='before')
    @classmethod
    def vector(cls, value):
        if (not isinstance(value, list) or len(value) != 512 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
            raise ValueError('Invalid reference vector')
        norm = math.sqrt(sum(v*v for v in value))
        if not .999 <= norm <= 1.001:
            raise ValueError('Reference vector must be L2 normalized')
        return value

    @field_validator('model')
    @classmethod
    def compatible(cls, value):
        if value != os.getenv('CLIP_MODEL'):
            raise ValueError('Incompatible reference; upload again')
        return value

    @field_validator('image_analysis')
    @classmethod
    def analysis(cls, value):
        # Store original zero-shot predictions, including scores and margins.
        if set(value) - set(ATTRIBUTE_LABELS): raise ValueError('Invalid analysis fields')
        for key, prediction in value.items():
            required = {'label','score','runner_up','runner_up_score','margin'}
            if not isinstance(prediction, dict) or set(prediction) != required:
                raise ValueError('Invalid prediction')
            if prediction['label'] not in ATTRIBUTE_LABELS[key] or prediction['runner_up'] not in ATTRIBUTE_LABELS[key]:
                raise ValueError('Invalid prediction label')
            for field in ('score','runner_up_score','margin'):
                number = prediction[field]
                if type(number) not in (float,int) or not math.isfinite(number) or not -2 <= number <= 2:
                    raise ValueError('Invalid prediction score')
            if prediction['margin'] < 0 or abs(prediction['score'] - prediction['runner_up_score'] - prediction['margin']) > 1e-5:
                raise ValueError('Invalid prediction margin')
        return value


ImageStrategy = Literal['attribute_guided', 'strict_attributes', 'pure_image_similarity',
                        'explicit_text_filtered_similarity', 'attributes_required']


class ImageActiveSearch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    search_type: Literal['image'] = 'image'
    mode: Literal['auto', 'exact', 'similar'] = 'auto'
    effective_image_strategy: ImageStrategy | None = None
    text_overrides: dict = Field(default_factory=dict)
    effective_filters: dict = Field(default_factory=dict)
    shown_product_ids: list[StrictStr] = Field(default_factory=list, max_length=4096)
    shown_point_ids: list[StrictStr] = Field(default_factory=list, max_length=4096)

    @field_validator('text_overrides')
    @classmethod
    def overrides(cls, value): return validate_overrides(value)

    @field_validator('effective_filters')
    @classmethod
    def filters(cls, value):
        if set(value) - set(ATTRIBUTE_LABELS): raise ValueError('Unsupported image filter')
        return ActiveSearch.attributes_only(value)

    @field_validator('shown_product_ids','shown_point_ids', mode='before')
    @classmethod
    def ids(cls, value): return ActiveSearch.identifiers(value)

    @field_validator('shown_point_ids')
    @classmethod
    def points(cls, value): return ActiveSearch.point_ids(value)

    @model_validator(mode='after')
    def mandatory(self):
        if any(self.effective_filters.get(k) != v for k,v in self.text_overrides.items()):
            raise ValueError('Explicit requirements must remain mandatory')
        if self.mode == 'similar' and self.effective_filters != self.text_overrides:
            raise ValueError('Similar image mode cannot include inferred filters')
        if self.effective_image_strategy is not None:
            from .hybrid_image_search import image_strategy
            if self.effective_image_strategy != image_strategy(self.mode, self.effective_filters, self.text_overrides):
                raise ValueError('Inconsistent effective image strategy')
        return self
