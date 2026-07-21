from __future__ import annotations

from pathlib import Path

from prompt_architect.adapters import AdapterRegistry
from prompt_architect.analyzers import ComplexityScorer, RequirementAnalyzer
from prompt_architect.compiler import PromptCompiler
from prompt_architect.context import ContextManager
from prompt_architect.evaluators import PromptReviewer
from prompt_architect.publisher import ArtifactPublisher
from prompt_architect.routing import StrategyRouter
from prompt_architect.schemas import (
    ComplexityAssessment,
    GenerationResult,
    Language,
    ReviewResult,
    RoutingDecision,
    TargetAgent,
    TaskSpec,
)


class PromptArchitectError(RuntimeError):
    pass


class MissingInformationError(PromptArchitectError):
    def __init__(self, task: TaskSpec) -> None:
        super().__init__("Critical task information is missing")
        self.task = task


class StrategyBlockedError(PromptArchitectError):
    def __init__(self, decision: RoutingDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


class QualityGateError(PromptArchitectError):
    def __init__(self, review: ReviewResult) -> None:
        super().__init__("Generated prompt failed the quality gate")
        self.review = review


class PromptArchitect:
    def __init__(self) -> None:
        self.requirements = RequirementAnalyzer()
        self.scorer = ComplexityScorer()
        self.router = StrategyRouter()
        self.context = ContextManager()
        self.adapters = AdapterRegistry()
        self.compiler = PromptCompiler(self.context)
        self.reviewer = PromptReviewer()
        self.publisher = ArtifactPublisher()

    def analyze(
        self,
        raw_request: str,
        *,
        target_agent: TargetAgent | None = None,
        deliverables: list[str] | None = None,
        known_context: list[str] | None = None,
        available_files: list[str] | None = None,
        constraints: list[str] | None = None,
        forbidden_actions: list[str] | None = None,
        tools: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        language: Language = Language.ZH_CN,
        allow_staged: bool = True,
    ) -> tuple[TaskSpec, ComplexityAssessment, RoutingDecision]:
        task = self.requirements.analyze(
            raw_request,
            target_agent=target_agent,
            deliverables=deliverables,
            known_context=known_context,
            available_files=available_files,
            constraints=constraints,
            forbidden_actions=forbidden_actions,
            tools=tools,
            acceptance_criteria=acceptance_criteria,
            language=language,
            allow_staged=allow_staged,
        )
        assessment = self.scorer.score(task)
        decision = self.router.route(task, assessment)
        selected = decision.selected_strategy or decision.recommended_strategy
        task = task.model_copy(
            update={"complexity_score": assessment.total_score, "prompt_strategy": selected}
        )
        return task, assessment, decision

    def generate(
        self,
        raw_request: str,
        *,
        target_agent: TargetAgent | None = None,
        deliverables: list[str] | None = None,
        known_context: list[str] | None = None,
        available_files: list[str] | None = None,
        constraints: list[str] | None = None,
        forbidden_actions: list[str] | None = None,
        tools: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        language: Language = Language.ZH_CN,
        allow_staged: bool = True,
        output_base: Path | None = None,
        context_base: Path | None = None,
    ) -> GenerationResult:
        result = self.build(
            raw_request,
            target_agent=target_agent,
            deliverables=deliverables,
            known_context=known_context,
            available_files=available_files,
            constraints=constraints,
            forbidden_actions=forbidden_actions,
            tools=tools,
            acceptance_criteria=acceptance_criteria,
            language=language,
            allow_staged=allow_staged,
            context_base=context_base,
        )
        output_dir = self.publisher.publish(result, output_base)
        return result.model_copy(update={"output_dir": output_dir})

    def build(
        self,
        raw_request: str,
        *,
        target_agent: TargetAgent | None = None,
        deliverables: list[str] | None = None,
        known_context: list[str] | None = None,
        available_files: list[str] | None = None,
        constraints: list[str] | None = None,
        forbidden_actions: list[str] | None = None,
        tools: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        language: Language = Language.ZH_CN,
        allow_staged: bool = True,
        context_base: Path | None = None,
    ) -> GenerationResult:
        """Compile and review a generation result without writing to disk."""
        task, assessment, decision = self.analyze(
            raw_request,
            target_agent=target_agent,
            deliverables=deliverables,
            known_context=known_context,
            available_files=available_files,
            constraints=constraints,
            forbidden_actions=forbidden_actions,
            tools=tools,
            acceptance_criteria=acceptance_criteria,
            language=language,
            allow_staged=allow_staged,
        )
        if task.has_blockers:
            raise MissingInformationError(task)
        if decision.blocked or decision.selected_strategy is None:
            raise StrategyBlockedError(decision)

        manifest = self.context.build(task, base_dir=context_base)
        guidance = self.adapters.get(task.target_agent).guidance(task)
        artifacts = self.compiler.compile(task, manifest, guidance, decision.selected_strategy)
        review = self.reviewer.review(task, artifacts, decision.selected_strategy)
        if not review.passed:
            artifacts = self.reviewer.repair(artifacts)
            review = self.reviewer.review(
                task, artifacts, decision.selected_strategy, repair_attempted=True
            )
        if not review.passed:
            raise QualityGateError(review)

        result = GenerationResult(
            task=task,
            assessment=assessment,
            context_manifest=manifest,
            artifacts=artifacts,
            review=review,
        )
        return result
