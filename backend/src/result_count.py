"""Per-request presentation limits; never persisted as search constraints."""
from dataclasses import dataclass

MIN_RESULT_COUNT = 1
DEFAULT_RESULT_COUNT = 8
MAX_RESULT_COUNT = 8

COUNT_INSTRUCTIONS = """
Extract result_count ONLY from the CURRENT user request, never history or active_search.
Use an integer for an explicit number of requested products/designs/examples/images,
including English number words and Simplified/Traditional Chinese/Cantonese:
7 shirts, two designs, another 5, 4 more, 6 examples, 找七件, 給我三張圖片,
再給我五件, 有冇兩件其他款. 'some'/'a few'/unspecified => null.
Size 10, year 2025, number 7 printed on a shirt, 3/4 sleeves and under $20
are NOT result counts; preserve their meaning and use null unless a separate count
is requested. Do not invent supported filters for these conditions.
Return the actual requested integer, including zero, negative and above-maximum
values; the application validates/caps it. Quantity alone is not an unsupported
image modification: 'show 5 similar ones' is noop with result_count 5.
Remove ONLY requested result quantity/delivery wording from resolved_query when
that field exists; preserve visual numbers, all garment meaning and supported
context. A self-contained counted request must not inherit old preferences.
"""
COUNT_SCHEMA = {"type": ["integer", "null"], "description": "Explicit current-request result quantity; null if unspecified or a number describes the garment."}


@dataclass(frozen=True)
class ResultCount:
    requested: int | None = None
    default: int = DEFAULT_RESULT_COUNT

    def __post_init__(self):
        if self.requested is not None and type(self.requested) is not int:
            raise ValueError("Invalid structured result count")
        if type(self.default) is not int or not MIN_RESULT_COUNT <= self.default <= MAX_RESULT_COUNT:
            raise ValueError("Invalid default result count")

    @property
    def valid(self):
        return self.requested is None or self.requested >= MIN_RESULT_COUNT

    @property
    def effective(self):
        return min(self.requested, MAX_RESULT_COUNT) if self.requested is not None and self.valid else self.default

    def metadata(self):
        return {"requested_count": self.requested,
                "effective_count": self.effective if self.valid else None,
                "count_capped": self.valid and self.requested is not None and self.requested > MAX_RESULT_COUNT}


def explain_cap(result):
    if result.get("count_capped"):
        result["text"] = f"I can show up to {MAX_RESULT_COUNT} designs at a time. " + result["text"]
    return result


INVALID_COUNT_MESSAGE = f"Please request at least {MIN_RESULT_COUNT} design. No search was run."
