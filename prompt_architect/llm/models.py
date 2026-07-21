from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from prompt_architect.schemas import RiskLevel, TargetAgent, TaskType


class ModelInfo(BaseModel):
    id: str
    owned_by: str = "deepseek"


class ModelUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "ModelUsage") -> "ModelUsage":
        return ModelUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class ProviderStatus(BaseModel):
    provider: Literal["deepseek"] = "deepseek"
    configured: bool = False
    source: Literal["environment", "credential_store", "none"] = "none"
    key_hint: str | None = None
    connected: bool = False
    default_model: str = "auto"
    models: list[ModelInfo] = Field(default_factory=list)
    message: str = ""


class LLMComplexityDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    reason: str = Field(min_length=1)


class LLMAnalysis(BaseModel):
    normalized_goal: str = Field(min_length=1)
    task_type: TaskType = TaskType.GENERAL
    task_subtypes: list[str] = Field(default_factory=list)
    target_agent: TargetAgent = TargetAgent.CHAT_MODEL
    deliverables: list[str] = Field(default_factory=list)
    known_context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    dimensions: dict[str, LLMComplexityDimension]
    questions: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "LLMAnalysis":
        expected = {
            "scope",
            "dependencies",
            "ambiguity",
            "risk",
            "context_size",
            "validation_difficulty",
        }
        if set(self.dimensions) != expected:
            raise ValueError("exactly the six supported complexity dimensions are required")
        return self


class LLMGeneratedFile(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=200_000)


class LLMGeneratedPackage(BaseModel):
    files: list[LLMGeneratedFile] = Field(min_length=1, max_length=12)


class LLMReviewIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "major", "critical"]
    message: str
    artifact: str | None = None


class LLMReview(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[LLMReviewIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pass(self) -> "LLMReview":
        if any(item.severity == "critical" for item in self.issues):
            self.passed = False
        return self
