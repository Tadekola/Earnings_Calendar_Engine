from __future__ import annotations

from pydantic import BaseModel

from app.core.enums import RecommendationClass


class ExplainFactorResponse(BaseModel):
    factor: str
    score: float
    weight: float
    weighted_contribution: float
    explanation: str
    data_points: dict[str, float | str | None] = {}


class ExplainResponse(BaseModel):
    ticker: str
    classification: RecommendationClass
    overall_score: float | None = None
    summary: str
    factors: list[ExplainFactorResponse] = []
    rejection_reasons: list[str] = []
    risk_warnings: list[str] = []
    data_quality_notes: list[str] = []
    recommendation_rationale: str | None = None


class RejectionResponse(BaseModel):
    ticker: str
    stage: str
    reason: str
    details: str | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    threshold_value: float | None = None


class RejectionsListResponse(BaseModel):
    total: int
    scan_run_id: str | None = None
    rejections: list[RejectionResponse]
