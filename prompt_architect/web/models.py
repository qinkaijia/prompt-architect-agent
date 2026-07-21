from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from prompt_architect.schemas import (
    ComplexityAssessment,
    Language,
    ReviewResult,
    RoutingDecision,
    TargetAgent,
    TaskSpec,
)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_request: str = Field(min_length=1, max_length=50_000)
    target_agent: TargetAgent | None = None
    deliverables: list[str] = Field(default_factory=list)
    known_context: list[str] = Field(default_factory=list)
    available_files: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    language: Language = Language.ZH_CN
    allow_staged: bool = True

    def service_kwargs(self) -> dict[str, Any]:
        data = self.model_dump()
        data["deliverables"] = data["deliverables"] or None
        data["known_context"] = data["known_context"] or None
        data["available_files"] = data["available_files"] or None
        data["constraints"] = data["constraints"] or None
        data["forbidden_actions"] = data["forbidden_actions"] or None
        data["tools"] = data["tools"] or None
        data["acceptance_criteria"] = data["acceptance_criteria"] or None
        return data


class AnalysisResponse(BaseModel):
    task: TaskSpec
    complexity: ComplexityAssessment
    routing: RoutingDecision
    blockers: list[str] = Field(default_factory=list)


class ArtifactMetadata(BaseModel):
    filename: str
    media_type: str = "text/markdown"
    size: int = 0
    download_url: str


class RunSummary(BaseModel):
    id: str
    created_at: datetime
    title: str
    normalized_goal: str
    target_agent: TargetAgent
    task_type: str
    strategy: str
    complexity_score: int
    quality_score: int
    status: Literal["ready", "archived"]


class RunDetail(RunSummary):
    sanitized_request: str
    output_dir: str
    task: dict[str, Any]
    complexity: dict[str, Any]
    review: ReviewResult
    artifacts: list[ArtifactMetadata] = Field(default_factory=list)


class RunListResponse(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class ImportRequest(BaseModel):
    path: str = Field(min_length=1)


class ImportResponse(BaseModel):
    imported: int


class ApiError(BaseModel):
    code: str
    message: str
    questions: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class CredentialRequest(BaseModel):
    api_key: str


class ModelSettingRequest(BaseModel):
    model_id: str = Field(default="auto", min_length=1, max_length=200)


class DesktopGrantRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=10)


class ContextGrantResponse(BaseModel):
    id: str
    files: list[dict[str, Any]] = Field(default_factory=list)


class AgentSessionCreate(GenerationRequest):
    model_id: str = "auto"
    offline_rules: bool = False
    context_grants: list[str] = Field(default_factory=list, max_length=10)


class AgentTurnRequest(BaseModel):
    answers: list[str] = Field(default_factory=list, max_length=3)


class AgentSessionSummary(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: Literal[
        "pending", "clarifying", "generating", "reviewing", "repairing",
        "completed", "failed", "cancelled"
    ]
    sanitized_request: str
    target_agent: str
    language: str
    provider: str
    model_id: str
    clarification_round: int = 0
    questions: list[str] = Field(default_factory=list)
    run_id: str | None = None
    last_error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class AgentSessionDetail(AgentSessionSummary):
    run: RunDetail | None = None
