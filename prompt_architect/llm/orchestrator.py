from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from prompt_architect.adapters import AdapterRegistry
from prompt_architect.context import ContextManager
from prompt_architect.evaluators import PromptReviewer
from prompt_architect.llm.context import ContextBundle
from prompt_architect.llm.deepseek import DeepSeekProvider, ProviderError
from prompt_architect.llm.models import (
    LLMAnalysis,
    LLMGeneratedPackage,
    LLMReview,
    ModelUsage,
)
from prompt_architect.routing import StrategyRouter
from prompt_architect.schemas import (
    ComplexityAssessment,
    ContextCategory,
    ContextItem,
    ContextManifest,
    DimensionScore,
    GenerationResult,
    Language,
    PromptArtifact,
    PromptStrategy,
    ReviewIssue,
    ReviewResult,
    ReviewSeverity,
    RiskLevel,
    RoutingDecision,
    TargetAgent,
    TaskSpec,
)
from prompt_architect.security import redact_secrets


class AgentQualityError(RuntimeError):
    def __init__(self, review: ReviewResult) -> None:
        super().__init__("智能生成结果未通过质量检查。")
        self.review = review


@dataclass
class AgentAnalysisResult:
    task: TaskSpec
    assessment: ComplexityAssessment
    routing: RoutingDecision
    usage: ModelUsage


@dataclass
class AgentGenerationResult:
    result: GenerationResult
    critic: LLMReview
    usage: ModelUsage
    repaired: bool


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AgentOrchestrator:
    def __init__(self, provider: DeepSeekProvider) -> None:
        self.provider = provider
        self.router = StrategyRouter()
        self.adapters = AdapterRegistry()
        self.context_manager = ContextManager()
        self.rule_reviewer = PromptReviewer()

    async def analyze(
        self,
        request: dict[str, Any],
        *,
        model: str,
        context: ContextBundle,
        answers: list[str] | None = None,
    ) -> AgentAnalysisResult:
        safe_request, _ = redact_secrets(str(request.get("raw_request", "")))
        payload = {
            "user_request": safe_request,
            "explicit_fields": {
                key: value
                for key, value in request.items()
                if key not in {"raw_request", "context_grants"} and value not in (None, [], "")
            },
            "clarification_answers": [redact_secrets(item)[0] for item in (answers or [])],
            "authorized_filenames": context.filenames,
            "authorized_context": context.text,
            "output_language": request.get("language", Language.ZH_CN.value),
        }
        analysis, usage = await self._call_schema(
            LLMAnalysis,
            [
                {"role": "system", "content": self._prompt("analyze")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            model=model,
            temperature=0.1,
        )
        dimensions = {
            key: DimensionScore(score=value.score, reason=value.reason, signals=[])
            for key, value in analysis.dimensions.items()
        }
        total = sum(item.score for item in dimensions.values())
        strategy = self._strategy(total)
        assessment = ComplexityAssessment(
            dimensions=dimensions,
            total_score=total,
            recommended_strategy=strategy,
            reason=analysis.reason,
        )
        language = Language(request.get("language", Language.ZH_CN.value))
        explicit_target = request.get("target_agent")
        target = TargetAgent(explicit_target) if explicit_target else analysis.target_agent
        deliverables = list(request.get("deliverables") or analysis.deliverables)
        acceptance = list(request.get("acceptance_criteria") or analysis.acceptance_criteria)
        if not analysis.questions:
            if not deliverables:
                deliverables = ["符合任务目标、可以直接使用的最终结果"]
            if not acceptance:
                acceptance = ["结果覆盖明确目标和约束", "所有结论区分已验证事实与假设"]
        task = TaskSpec(
            raw_request=str(request.get("raw_request", "")),
            sanitized_request=safe_request,
            normalized_goal=analysis.normalized_goal,
            task_type=analysis.task_type,
            task_subtypes=analysis.task_subtypes,
            target_agent=target,
            deliverables=deliverables,
            known_context=list(request.get("known_context") or analysis.known_context),
            available_files=context.filenames,
            constraints=list(request.get("constraints") or analysis.constraints),
            forbidden_actions=list(request.get("forbidden_actions") or analysis.forbidden_actions),
            tools=list(request.get("tools") or analysis.tools),
            missing_information=analysis.missing_information,
            acceptance_criteria=acceptance,
            risk_level=analysis.risk_level if isinstance(analysis.risk_level, RiskLevel) else RiskLevel(analysis.risk_level),
            complexity_score=total,
            prompt_strategy=strategy,
            language=language,
            allow_staged=bool(request.get("allow_staged", True)),
            blocking_questions=analysis.questions,
        )
        routing = self.router.route(task, assessment)
        if routing.selected_strategy:
            task = task.model_copy(update={"prompt_strategy": routing.selected_strategy})
        return AgentAnalysisResult(task, assessment, routing, usage)

    async def generate(
        self,
        analysis: AgentAnalysisResult,
        *,
        model: str,
        context: ContextBundle,
        on_stage: Callable[[str], Awaitable[None]] | None = None,
    ) -> AgentGenerationResult:
        task = analysis.task
        strategy = analysis.routing.selected_strategy
        if strategy is None:
            raise AgentQualityError(
                ReviewResult(
                    passed=False,
                    score=0,
                    issues=[ReviewIssue(code="strategy_blocked", severity=ReviewSeverity.CRITICAL, message=analysis.routing.reason)],
                )
            )
        manifest = ContextManifest(
            items=[
                ContextItem(
                    path=name,
                    category=ContextCategory.REQUIRED,
                    purpose="用户已授权本次任务按需读取。",
                    exists=True,
                )
                for name in context.filenames
            ],
            notes=context.warnings,
        )
        expected = self._expected_files(strategy)
        guidance = self.adapters.get(task.target_agent).guidance(task)
        generation_payload = {
            "task": task.model_dump(mode="json"),
            "complexity": analysis.assessment.model_dump(mode="json"),
            "strategy": strategy.value,
            "required_filenames": expected,
            "target_adapter": guidance.model_dump(mode="json"),
            "context_manifest": manifest.model_dump(mode="json"),
            "authorized_context": context.text,
        }
        if on_stage:
            await on_stage("generating")
        package, usage = await self._call_schema(
            LLMGeneratedPackage,
            [
                {"role": "system", "content": self._prompt("generate")},
                {"role": "user", "content": json.dumps(generation_payload, ensure_ascii=False)},
            ],
            model=model,
            temperature=0.25,
        )
        artifacts = self._artifacts(package, expected)
        artifacts.append(
            PromptArtifact(
                filename="CONTEXT_MANIFEST.md",
                content=self.context_manager.render_markdown(task, manifest),
            )
        )
        if on_stage:
            await on_stage("reviewing")
        critic, critic_usage = await self._critic(task, artifacts, strategy, model)
        usage += critic_usage
        rule_review = self.rule_reviewer.review(task, artifacts, strategy)
        repaired = False
        if not critic.passed or not rule_review.passed:
            repaired = True
            if on_stage:
                await on_stage("repairing")
            repair_payload = {
                "task": task.model_dump(mode="json"),
                "required_filenames": expected,
                "files": [item.model_dump() for item in artifacts if item.filename != "CONTEXT_MANIFEST.md"],
                "model_review": critic.model_dump(mode="json"),
                "rule_review": rule_review.model_dump(mode="json"),
            }
            repaired_package, repair_usage = await self._call_schema(
                LLMGeneratedPackage,
                [
                    {"role": "system", "content": self._prompt("repair")},
                    {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=False)},
                ],
                model=model,
                temperature=0.1,
            )
            usage += repair_usage
            artifacts = self._artifacts(repaired_package, expected)
            artifacts.append(
                PromptArtifact(
                    filename="CONTEXT_MANIFEST.md",
                    content=self.context_manager.render_markdown(task, manifest),
                )
            )
            if on_stage:
                await on_stage("reviewing")
            critic, critic_usage = await self._critic(task, artifacts, strategy, model)
            usage += critic_usage
            rule_review = self.rule_reviewer.review(task, artifacts, strategy, repair_attempted=True)
        combined = self._combined_review(task, critic, rule_review, repaired)
        if not combined.passed:
            raise AgentQualityError(combined)
        return AgentGenerationResult(
            GenerationResult(
                task=task,
                assessment=analysis.assessment,
                context_manifest=manifest,
                artifacts=artifacts,
                review=combined,
            ),
            critic,
            usage,
            repaired,
        )

    async def _critic(
        self,
        task: TaskSpec,
        artifacts: list[PromptArtifact],
        strategy: PromptStrategy,
        model: str,
    ) -> tuple[LLMReview, ModelUsage]:
        return await self._call_schema(
            LLMReview,
            [
                {"role": "system", "content": self._prompt("review")},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": task.model_dump(mode="json"),
                            "strategy": strategy.value,
                            "files": [item.model_dump() for item in artifacts],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            model=model,
            temperature=0.0,
        )

    async def _call_schema(
        self,
        schema: type[SchemaT],
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
    ) -> tuple[SchemaT, ModelUsage]:
        payload, usage = await self.provider.complete_json(messages, model=model, temperature=temperature)
        try:
            return schema.model_validate(payload), usage
        except ValidationError as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": "上一个 JSON 不符合要求。只返回修正后的完整 JSON。校验错误："
                    + str(first_error)[:4000],
                },
            ]
            repaired, repair_usage = await self.provider.complete_json(
                repair_messages, model=model, temperature=0.0
            )
            try:
                return schema.model_validate(repaired), usage + repair_usage
            except ValidationError as exc:
                raise ProviderError("invalid_structured_output", "DeepSeek 未能返回符合要求的结构化结果。") from exc

    @staticmethod
    def _strategy(score: int) -> PromptStrategy:
        if score <= 4:
            return PromptStrategy.COMPACT
        if score <= 8:
            return PromptStrategy.STRUCTURED
        if score <= 13:
            return PromptStrategy.STAGED
        return PromptStrategy.PROJECT

    @staticmethod
    def _expected_files(strategy: PromptStrategy) -> list[str]:
        if strategy in {PromptStrategy.COMPACT, PromptStrategy.STRUCTURED}:
            return ["PROMPT.md"]
        if strategy == PromptStrategy.STAGED:
            return [
                "STAGE_INDEX.md",
                "STAGE_01_ANALYZE.md",
                "STAGE_02_DESIGN.md",
                "STAGE_03_IMPLEMENT.md",
                "STAGE_04_TEST.md",
                "STAGE_05_DOCUMENT.md",
            ]
        return [
            "PROJECT_BRIEF.md",
            "ARCHITECTURE_PROMPT.md",
            "IMPLEMENTATION_PROMPT.md",
            "TEST_PROMPT.md",
            "REVIEW_PROMPT.md",
            "ACCEPTANCE_CRITERIA.md",
        ]

    @staticmethod
    def _artifacts(package: LLMGeneratedPackage, expected: list[str]) -> list[PromptArtifact]:
        names = [item.filename for item in package.files]
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ProviderError("invalid_artifact_set", "DeepSeek 返回的提示词文件集合不完整。")
        by_name = {item.filename: item.content for item in package.files}
        for name in names:
            if "/" in name or "\\" in name or name in {".", ".."}:
                raise ProviderError("invalid_filename", "DeepSeek 返回了不安全的文件名。")
        return [PromptArtifact(filename=name, content=by_name[name].strip() + "\n") for name in expected]

    @staticmethod
    def _combined_review(
        task: TaskSpec,
        critic: LLMReview,
        rule: ReviewResult,
        repaired: bool,
    ) -> ReviewResult:
        model_issues = [
            ReviewIssue(
                code=f"model_{item.code}",
                severity=ReviewSeverity(item.severity),
                message=item.message,
                artifact=item.artifact,
            )
            for item in critic.issues
        ]
        issues = [*rule.issues, *model_issues]
        passed = critic.passed and rule.passed and not any(
            item.severity == ReviewSeverity.CRITICAL for item in issues
        )
        suggestions = list(dict.fromkeys([*rule.suggestions, *critic.suggestions]))
        return ReviewResult(
            passed=passed,
            score=min(rule.score, critic.score),
            issues=issues,
            suggestions=suggestions,
            repair_attempted=repaired,
        )

    @staticmethod
    def _prompt(name: str) -> str:
        return files("prompt_architect.llm").joinpath("prompts", f"{name}.txt").read_text(encoding="utf-8")
