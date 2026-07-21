from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Language(StrEnum):
    ZH_CN = "zh-CN"
    EN = "en"


class TaskType(StrEnum):
    SOFTWARE_DEVELOPMENT = "software_development"
    CODE_DEBUGGING = "code_debugging"
    REPOSITORY_REFACTORING = "repository_refactoring"
    EMBEDDED_SYSTEM = "embedded_system"
    HARDWARE_DESIGN = "hardware_design"
    SIMULATION = "simulation"
    RESEARCH = "research"
    DOCUMENT_WRITING = "document_writing"
    DATA_ANALYSIS = "data_analysis"
    IMAGE_DESIGN = "image_design"
    PRESENTATION = "presentation"
    AUTOMATION = "automation"
    AGENT_DEVELOPMENT = "agent_development"
    LEARNING = "learning"
    GENERAL = "general"


class TargetAgent(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    CHAT_MODEL = "chat_model"
    IMAGE_MODEL = "image_model"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PromptStrategy(StrEnum):
    COMPACT = "compact_prompt"
    STRUCTURED = "structured_prompt"
    STAGED = "staged_prompt"
    PROJECT = "project_prompt_package"


class TaskSpec(BaseModel):
    """Normalized, explainable representation of one user task."""

    model_config = ConfigDict(extra="forbid")

    raw_request: str = Field(repr=False, exclude=True, description="Original input; never persisted")
    sanitized_request: str = Field(description="Secret-redacted request safe for persistence")
    normalized_goal: str = Field(default="", description="Concrete goal normalized from the request")
    task_type: TaskType = TaskType.GENERAL
    task_subtypes: list[str] = Field(default_factory=list)
    target_agent: TargetAgent = TargetAgent.CHAT_MODEL
    deliverables: list[str] = Field(default_factory=list)
    known_context: list[str] = Field(default_factory=list)
    available_files: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    complexity_score: int = Field(default=0, ge=0, le=18)
    prompt_strategy: PromptStrategy = PromptStrategy.COMPACT
    language: Language = Language.ZH_CN
    allow_staged: bool = True
    inferred_fields: list[str] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)
    blocking_questions: list[str] = Field(default_factory=list)

    @property
    def has_blockers(self) -> bool:
        return bool(self.blocking_questions)
