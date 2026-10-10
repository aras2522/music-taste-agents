from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TasteRequest(BaseModel):
    taste: str = Field(..., min_length=2, max_length=2000, description="Artists, albums, genres, or free-text taste")
    artists: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=5, ge=1, le=9)


def _as_optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


class SourcePick(BaseModel):
    artist: str
    album: str
    year: str | None = None
    url: str | None = None
    why: str
    score_or_signal: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("year", "score_or_signal", "url", mode="before")
    @classmethod
    def coerce_optional_str(cls, value: Any) -> str | None:
        return _as_optional_str(value)


class AgentResult(BaseModel):
    source: Literal["pitchfork", "rym"]
    picks: list[SourcePick] = Field(default_factory=list)
    notes: str = ""
    error: str | None = None


class MergedRecommendation(BaseModel):
    artist: str
    album: str
    year: str | None = None
    urls: dict[str, str] = Field(default_factory=dict)
    why: str
    sources: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)

    @field_validator("year", mode="before")
    @classmethod
    def coerce_year(cls, value: Any) -> str | None:
        return _as_optional_str(value)


class RecommendResponse(BaseModel):
    taste: str
    recommendations: list[MergedRecommendation]
    agents: list[AgentResult]
    message: str | None = None
