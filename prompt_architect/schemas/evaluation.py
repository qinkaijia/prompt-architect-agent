from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from prompt_architect.schemas.task import PromptStrategy


class DimensionScore(BaseModel):
    score: int = Field(ge=0, le=3)
    reason: str
    signals: list[str] = Field(default_factory=list)


class ComplexityAssessment(BaseModel):
    dimensions: dict[str, DimensionScore]
    total_score: int = Field(ge=0, le=18)
    recommended_strategy: PromptStrategy
    reason: str

    @model_validator(mode="after")
    def validate_total(self) -> "ComplexityAssessment":
        if sum(item.score for item in self.dimensions.values()) != self.total_score:
            raise ValueError("total_score must equal the six dimension scores")
        if len(self.dimensions) != 6:
            raise ValueError("exactly six complexity dimensions are required")
        return self


class RoutingDecision(BaseModel):
    recommended_strategy: PromptStrategy
    selected_strategy: PromptStrategy | None
    blocked: bool = False
    reason: str
    warnings: list[str] = Field(default_factory=list)


class ReviewSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    MAJOR = "major"
    CRITICAL = "critical"


class ReviewIssue(BaseModel):
    code: str
    severity: ReviewSeverity
    message: str
    artifact: str | None = None
    repairable: bool = False


class ReviewResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[ReviewIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    repair_attempted: bool = False
