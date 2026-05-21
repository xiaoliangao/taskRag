"""Translation endpoint backed by DeepLX."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep
from app.services.translation_service import (
    TranslationResult,
    is_configured,
    translate,
)

router = APIRouter()


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    # ISO 2-letter or DeepL-style codes ("ZH", "EN", "JA", ...). Omit → auto.
    target_lang: str | None = Field(default=None, max_length=8)


class TranslateResponse(BaseModel):
    text: str
    source_lang: str
    target_lang: str
    cached: bool


class TranslateStatusResponse(BaseModel):
    enabled: bool


@router.get("/status", response_model=TranslateStatusResponse)
async def translate_status(_user: CurrentUserDep) -> TranslateStatusResponse:
    """Lets the UI hide the translate button when DeepLX isn't configured."""
    return TranslateStatusResponse(enabled=is_configured())


@router.post("", response_model=TranslateResponse)
async def translate_route(
    body: TranslateRequest, _user: CurrentUserDep
) -> TranslateResponse:
    result: TranslationResult = await translate(body.text, body.target_lang)
    return TranslateResponse(
        text=result.text,
        source_lang=result.source_lang,
        target_lang=result.target_lang,
        cached=result.cached,
    )
