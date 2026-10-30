"""HTTP transport for the existing GarmentAgent; no search logic lives here."""

import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from src.asset_paths import IMAGE_ROOT, resolve_catalog_path
from src.conversation_context import MAX_CONTEXT_INPUT_MESSAGES, MAX_CONTEXT_TEXT
from src.search_state import ActiveSearch, add_displayed
from src.image_reference import ImageReference, ImageActiveSearch, ImageStrategy
from src.hybrid_image_search import image_strategy
from src.image_messages import _mixed_message
from src.image_upload import ImageUploadSizeLimit, MAX_IMAGE_BYTES, decode_image


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)
app = FastAPI(title="Garment Chat API")
app.mount("/images", StaticFiles(directory=IMAGE_ROOT, follow_symlink=False), name="images")

app.add_middleware(ImageUploadSizeLimit)
from src.json_size_limit import ContinuationSizeLimit
from src.result_count import (ResultCount, DEFAULT_RESULT_COUNT, MIN_RESULT_COUNT,
    MAX_RESULT_COUNT, INVALID_COUNT_MESSAGE, explain_cap)
app.add_middleware(ContinuationSizeLimit)

DEFAULT_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (3000, 5173, 8000)
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_override_extractor = None
_image_search = None
_agent = None
_agent_lock = Lock()


class ContextMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: StrictStr = Field(min_length=1, max_length=MAX_CONTEXT_TEXT)


class ChatRequest(BaseModel):
    active_search: ActiveSearch | ImageActiveSearch | None = None
    query: StrictStr
    mode: Literal["auto", "exact", "similar", "default"] = "auto"
    context: list[ContextMessage] = Field(default_factory=list, max_length=MAX_CONTEXT_INPUT_MESSAGES)

    @field_validator("mode")
    @classmethod
    def legacy_mode(cls, value: str) -> str:
        return "auto" if value == "default" else value

    @field_validator("query")
    @classmethod
    def require_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Query cannot be empty.")
        return value


class SearchResults(BaseModel):
    exact: list[dict[str, Any]]
    similar: list[dict[str, Any]]


class ChatResponse(BaseModel):
    requested_mode: Literal["auto", "exact", "similar"] | None = None
    effective_mode: Literal["auto", "exact", "similar"] | None = None
    effective_image_strategy: ImageStrategy | None = None
    requested_count: int | None = None
    effective_count: int | None = None
    count_capped: bool = False
    search_type: str | None = None
    continuation: bool | None = None
    text_overrides: dict | None = None
    image_analysis: dict | None = None
    active_search: ActiveSearch | ImageActiveSearch | None = None
    relation_to_context: str | None = None
    has_more: bool | None = None
    text: StrictStr
    response_id: StrictStr
    closing_text: StrictStr = ""
    resolved_query: StrictStr = ""
    search_strategy: Literal["exact", "similar", "both", "none"] = "none"
    intent: Literal["search", "informational", "unrelated", "clarification"] = "search"
    products: list[dict[str, Any]]
    search_results: SearchResults


def image_url_for(image_path: Any) -> str | None:
    """Map only local paths inside IMAGE_ROOT to root-relative HTTP URLs."""
    if not isinstance(image_path, str) or not image_path:
        return None
    try:
        path = Path(image_path)
        if ".." in path.parts:
            return None
        if not path.is_absolute():
            path = resolve_catalog_path(path)
        relative = path.resolve().relative_to(IMAGE_ROOT)
        if relative == Path("."):
            return None
        return "/images/" + quote(relative.as_posix(), safe="/")
    except (ValueError, OSError, RuntimeError):
        return None


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Do not echo request values or validation exception context to clients.
    fields = {error["loc"][-1] for error in exc.errors() if error["loc"]}
    if request.url.path == "/api/image-search/continue":
        detail = "Saved image context is invalid or incompatible. Please upload the reference image again."
    elif request.url.path == "/api/image-search":
        detail = f"Provide an image upload, an integer limit between {MIN_RESULT_COUNT} and {MAX_RESULT_COUNT}, and optional query up to 2000 characters."
    elif any("active_search" in error["loc"] for error in exc.errors()):
        detail = "Active search state has an invalid shape, value, or exceeds its size limit."
    elif any("context" in error["loc"] for error in exc.errors()):
        detail = "Context must contain up to 1000 user/assistant text messages, each at most 10000 characters."
    elif "mode" in fields:
        detail = "Search mode must be auto, exact, or similar (default is a legacy alias)."
    elif "query" in fields:
        detail = "Query must be a non-empty string."
    else:
        detail = "Request body must be a JSON object with query and optional mode."
    return JSONResponse(status_code=422, content={"detail": detail})


def _create_agent():
    # Match existing backend configuration, including the SDK's key fallback.
    required = ("OPENAI_MODEL", "QDRANT_URL", "QDRANT_COLLECTION")
    if any(not os.getenv(name, "").strip() for name in required) or not (
        os.getenv("POE_API", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    ):
        raise HTTPException(
            status_code=503,
            detail="Backend configuration is incomplete. Check the server's .env configuration.",
        )
    try:
        # Keep health checks and validation independent of model loading.
        from chatbot import GarmentAgent

        return GarmentAgent(product_search=_image_search) if _image_search is not None else GarmentAgent()
    except Exception as exc:
        logger.error("GarmentAgent initialization failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Chat backend could not initialize. Check server configuration and dependencies.",
        ) from None


@app.get("/api/health")
def health():
    """Process liveness only; does not initialize or query the backend."""
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    global _agent
    # Serialize use of the shared model/clients, whose thread safety is unknown.
    # A sync route runs in FastAPI's thread pool, leaving health checks responsive.
    with _agent_lock:
        if _agent is None:
            _agent = _create_agent()
        try:
            kwargs = {"query": request.query, "mode": request.mode}
            if request.context:
                kwargs["context"] = [item.model_dump() for item in request.context]
            if request.active_search is not None:
                kwargs["active_search"] = request.active_search.model_dump()
            result = _agent.respond(**kwargs)
            response = ChatResponse(**result).model_copy(deep=True)
            for products in (response.products, response.search_results.exact,
                             response.search_results.similar):
                for product in products:
                    product["image_url"] = image_url_for(product.get("image_path"))
            return response
        except Exception as exc:
            logger.error("GarmentAgent request failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="Chat backend failed to complete the request. Please try again.",
            ) from None


class ImageSearchResponse(BaseModel):
    requested_mode: Literal["auto", "exact", "similar"] | None = None
    effective_mode: Literal["auto", "exact", "similar"] | None = None
    effective_image_strategy: ImageStrategy | None = None
    requested_count: int | None = None
    effective_count: int | None = None
    count_capped: bool = False
    image_reference: ImageReference | None = None
    active_search: ImageActiveSearch | None = None
    text_analysis: dict[str, Any] | None = None
    resolved_attributes: dict[str, Any] | None = None
    search_strategy: str | None = None
    intent: str | None = None
    image_analysis: dict[str, Any] | None = None
    text: str
    search_type: Literal["image"] = "image"
    products: list[dict[str, Any]]
    closing_text: str


def _get_image_search():
    """Called under _agent_lock; image-only usage never constructs an agent."""
    global _image_search
    if _image_search is None:
        if _agent is not None:
            _image_search = _agent.product_search
        else:
            try:
                from src.product_search import ProductSearch
                _image_search = ProductSearch()
            except Exception as exc:
                logger.error("Image search initialization failed (%s)", type(exc).__name__)
                raise HTTPException(503, "Image search could not initialize. Check server configuration.") from None
    return _image_search


def _get_override_extractor():
    global _override_extractor
    if _agent is not None:
        return _agent.attribute_extractor
    if _override_extractor is None:
        if not os.getenv("OPENAI_MODEL") or not (os.getenv("POE_API") or os.getenv("OPENAI_API_KEY")):
            raise RuntimeError("Text modification configuration incomplete")
        from src.query_attribute_extractor import QueryAttributeExtractor
        _override_extractor = QueryAttributeExtractor()
    return _override_extractor


@app.post("/api/image-search", response_model=ImageSearchResponse)
def image_search(image: UploadFile = File(...), limit: int = Form(DEFAULT_RESULT_COUNT, ge=MIN_RESULT_COUNT, le=MAX_RESULT_COUNT),
                 query: str = Form("", max_length=2000),
                 mode: Literal["auto", "exact", "similar"] = Form("auto")):
    # A sync route keeps decoding and model inference off the event loop.
    try:
        data = image.file.read(MAX_IMAGE_BYTES + 1)
        decoded = decode_image(data, image.content_type)
    finally:
        image.file.close()
    try:
        with _agent_lock:
            try:
                analysis = None
                if query.strip():
                    analysis = _get_override_extractor().extract_image_overrides(query.strip())
                    if analysis["intent"] in {"unsupported", "unrelated", "clarification"}:
                        return ImageSearchResponse(text=_mixed_message(analysis, []), products=[],
                            requested_count=ResultCount(analysis.get("result_count"), default=limit).requested,
                            closing_text="", text_analysis=analysis, requested_mode=mode, effective_mode=mode, search_strategy="none",
                            intent="unrelated" if analysis["intent"] == "unrelated" else "clarification")
                count = ResultCount(analysis.get("result_count") if analysis else None, default=limit)
                if not count.valid:
                    return ImageSearchResponse(text=INVALID_COUNT_MESSAGE, products=[], closing_text="",
                        intent="clarification", requested_mode=mode, search_strategy="none", **count.metadata())
                limit = count.effective
                search = _get_image_search()
                if analysis and analysis["intent"] == "modify":
                    result = search.search_by_image_with_overrides(decoded, analysis["overrides"], limit=limit, **({"mode": mode} if mode != "auto" else {}))
                else:
                    result = search.search_by_image_hybrid(decoded, limit=limit, **({"mode": mode} if mode != "auto" else {}))
                overrides = analysis["overrides"] if analysis and analysis["intent"] == "modify" else {}
                filters = result.get("image_analysis", {}).get("filters_used", overrides)
                strategy = result.get("effective_image_strategy") or image_strategy(mode, filters, overrides)
                strict = strategy == "strict_attributes"
                needs_attributes = strategy == "attributes_required"
                products = [{**product, "match_type": "exact" if strict else "similar",
                             "image_url": image_url_for(product.get("image_path"))}
                            for product in result["results"][:limit]]
                if needs_attributes:
                    intro = "No reliable image attributes are available for Exact matching. Add an explicit attribute such as a color, or switch to Similar."
                elif strict:
                    intro = (f"I found {len(products)} designs matching the strict image attributes." if products else
                             "No designs matched the strict image attributes. Switch to Auto or Similar to broaden the search.")
                elif overrides:
                    intro = _mixed_message(analysis, products)
                else:
                    intro = ("I found visually similar T-shirts based on your uploaded image." if products else
                             "No visually similar T-shirts were found.")
                response = ImageSearchResponse(
                    **count.metadata(), requested_mode=mode, effective_mode=mode, effective_image_strategy=strategy,
                    intent="clarification" if needs_attributes else "search",
                    text=intro,
                    image_reference=result.get("image_reference"),
                    active_search=(add_displayed(ImageActiveSearch(
                        mode=mode, effective_image_strategy=strategy,
                        text_overrides=overrides, effective_filters=filters), products)
                        if result.get("image_reference") else None),
                    products=products, image_analysis=result.get("image_analysis"),
                    text_analysis=analysis, resolved_attributes=result.get("resolved_attributes"),
                    search_strategy="none" if needs_attributes else "exact" if strict else ("image_with_attribute_override" if overrides else None),
                    closing_text="Click any design to inspect its details." if products else "",
                )
                if strict and analysis and analysis.get("unsupported_text"):
                    response.text += " These additional changes were not applied: " + "; ".join(analysis["unsupported_text"]) + "."
                return explain_cap(response.model_dump())
            except HTTPException:
                raise
            except Exception as exc:
                logger.error("Image search failed (%s)", type(exc).__name__)
                raise HTTPException(502, "Image search failed to complete. Please try again.") from None
    finally:
        decoded.close()


class ImageContinueRequest(ChatRequest):
    model_config = ConfigDict(extra="forbid")
    reference_image: ImageReference
    query: StrictStr = Field(min_length=1, max_length=2000)


@app.post("/api/image-search/continue", response_model=ChatResponse)
def continue_image(request: ImageContinueRequest):
    """Same agent resolver can select image continuation, independent text or Q&A."""
    global _agent
    with _agent_lock:
        if _agent is None:
            _agent = _create_agent()
        try:
            result = _agent.respond(query=request.query, mode=request.mode,
                context=[item.model_dump() for item in request.context],
                active_search=request.active_search.model_dump() if request.active_search else None,
                reference_image=request.reference_image.model_dump())
            response = ChatResponse(**result).model_copy(deep=True)
            for products in (response.products,response.search_results.exact,response.search_results.similar):
                for product in products: product["image_url"] = image_url_for(product.get("image_path"))
            return response
        except Exception as exc:
            logger.error("Image continuation failed (%s)", type(exc).__name__)
            raise HTTPException(502, "Image continuation failed. Please try again.") from None
