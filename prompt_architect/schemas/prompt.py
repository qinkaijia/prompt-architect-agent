from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from prompt_architect.schemas.evaluation import ComplexityAssessment, ReviewResult
from prompt_architect.schemas.task import TaskSpec


class ContextCategory(StrEnum):
    REQUIRED = "required_context"
    OPTIONAL = "optional_context"
    REFERENCE_ONLY = "reference_only"
    IGNORED = "ignored_context"


class ContextItem(BaseModel):
    path: str
    category: ContextCategory
    purpose: str
    sections: list[str] = Field(default_factory=list)
    read_when: str | None = None
    exists: bool | None = None


class ContextManifest(BaseModel):
    items: list[ContextItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def by_category(self, category: ContextCategory) -> list[ContextItem]:
        return [item for item in self.items if item.category == category]


class AdapterGuidance(BaseModel):
    role: str
    execution_rules: list[str] = Field(default_factory=list)
    final_report: list[str] = Field(default_factory=list)
    required_dimensions: list[str] = Field(default_factory=list)


class PromptArtifact(BaseModel):
    filename: str
    content: str


class GenerationResult(BaseModel):
    task: TaskSpec
    assessment: ComplexityAssessment
    context_manifest: ContextManifest
    artifacts: list[PromptArtifact]
    review: ReviewResult
    output_dir: Path | None = None
