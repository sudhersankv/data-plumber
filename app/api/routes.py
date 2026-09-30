from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.api import AdaptRequest, AdaptResponse
from app.models.internal import AdaptError, UpstreamLLMError
from app.services.llm_client import FireworksClient, LLMClient
from app.services.pipeline import adapt

logger = logging.getLogger("data_plumber")
router = APIRouter()


@lru_cache(maxsize=1)
def _fireworks_client() -> FireworksClient:
    settings = get_settings()
    return FireworksClient(
        api_key=settings.fireworks_api_key,
        model=settings.fireworks_model,
        base_url=settings.fireworks_base_url,
        timeout_s=settings.llm_timeout_s,
    )


def get_llm_client() -> LLMClient:
    if not get_settings().fireworks_api_key:
        raise HTTPException(status_code=503, detail="FIREWORKS_API_KEY is not configured")
    return _fireworks_client()


@router.get("/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/adapt", response_model=AdaptResponse, response_model_exclude_none=True)
def adapt_endpoint(
    request: AdaptRequest,
    debug: bool = Query(False, description="Include the per-field trace in the response."),
    client: LLMClient = Depends(get_llm_client),
) -> JSONResponse:
    try:
        result = adapt(
            content_type=request.source.content_type,
            data=request.source.data,
            target_schema=request.target_schema,
            instructions=request.instructions,
            client=client,
        )
    except AdaptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UpstreamLLMError as exc:
        logger.warning("model call failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info("adapt valid=%s warnings=%d repaired=%s", result.valid, len(result.warnings), result.repaired)
    for entry in result.trace:
        logger.debug("trace %s", entry)
    return JSONResponse(result.to_response(debug=debug))
