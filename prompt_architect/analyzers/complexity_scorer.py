from __future__ import annotations

from prompt_architect.config_loader import load_config
from prompt_architect.schemas import (
    ComplexityAssessment,
    DimensionScore,
    Language,
    PromptStrategy,
    RiskLevel,
    TaskSpec,
    TaskType,
)


class ComplexityScorer:
    DIMENSIONS = ("scope", "dependencies", "ambiguity", "risk", "context_size", "validation_difficulty")

    def __init__(self) -> None:
        self.rules = load_config("complexity_rules.yaml")

    def score(self, task: TaskSpec) -> ComplexityAssessment:
        text = task.sanitized_request.casefold()
        dimensions = {
            "scope": self._scope(task, text),
            "dependencies": self._dependencies(task, text),
            "ambiguity": self._ambiguity(task),
            "risk": self._risk(task),
            "context_size": self._context(task, text),
            "validation_difficulty": self._validation(task, text),
        }
        total = sum(item.score for item in dimensions.values())
        strategy = self.strategy_for_score(total)
        if task.language == Language.ZH_CN:
            reason = f"六维总分为 {total}/18，因此推荐 {strategy.value}。"
        else:
            reason = f"The six dimensions total {total}/18, so {strategy.value} is recommended."
        return ComplexityAssessment(
            dimensions=dimensions,
            total_score=total,
            recommended_strategy=strategy,
            reason=reason,
        )

    @staticmethod
    def strategy_for_score(score: int) -> PromptStrategy:
        if score <= 4:
            return PromptStrategy.COMPACT
        if score <= 8:
            return PromptStrategy.STRUCTURED
        if score <= 13:
            return PromptStrategy.STAGED
        return PromptStrategy.PROJECT

    def _keyword_level(self, section: str, text: str) -> tuple[int, list[str]]:
        rules = self.rules[section]
        for score in (3, 2, 1):
            signals = [item for item in rules.get(f"level_{score}", []) if item.casefold() in text]
            if signals:
                return score, signals
        return 0, []

    def _dimension(self, task: TaskSpec, score: int, signals: list[str], zh: str, en: str) -> DimensionScore:
        return DimensionScore(score=score, signals=signals, reason=zh if task.language == Language.ZH_CN else en)

    def _scope(self, task: TaskSpec, text: str) -> DimensionScore:
        score, signals = self._keyword_level("scope", text)
        domains = [x for x in ("传感器", "mqtt", "qt", "语音", "视觉", "大模型", "sensor", "vision") if x in text]
        if task.task_type == TaskType.EMBEDDED_SYSTEM and len(domains) >= 3:
            score, signals = 3, domains
        elif score == 0 and task.task_type in {TaskType.SOFTWARE_DEVELOPMENT, TaskType.IMAGE_DESIGN}:
            score = 1
        return self._dimension(task, score, signals, f"任务范围匹配 {score} 级规则。", f"Task scope matches level {score} rules.")

    def _dependencies(self, task: TaskSpec, text: str) -> DimensionScore:
        score, signals = self._keyword_level("dependencies", text)
        domains = [x for x in ("传感器", "mqtt", "qt", "语音", "视觉", "大模型", "sensor", "vision") if x in text]
        if len(domains) >= 3:
            score, signals = 3, domains
        elif score < 2 and (("现有" in text and "项目" in text) or ("existing" in text and "project" in text)):
            score, signals = 2, ["existing_project"]
        elif score == 0 and (task.available_files or task.task_type in {TaskType.SOFTWARE_DEVELOPMENT, TaskType.CODE_DEBUGGING}):
            score = 1
        return self._dimension(task, score, signals, f"依赖规模匹配 {score} 级规则。", f"Dependency load matches level {score} rules.")

    def _ambiguity(self, task: TaskSpec) -> DimensionScore:
        if task.has_blockers:
            score, signals = 3, task.missing_information
        elif task.missing_information:
            score, signals = 2, task.missing_information
        elif task.inferred_fields:
            score, signals = 1, task.inferred_fields
        else:
            score, signals = 0, []
        return self._dimension(task, score, signals, f"需求歧义程度为 {score} 级。", f"Requirement ambiguity is level {score}.")

    def _risk(self, task: TaskSpec) -> DimensionScore:
        mapping = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        score = mapping[task.risk_level]
        return self._dimension(task, score, [task.risk_level.value], f"操作风险为 {task.risk_level.value}。", f"Operational risk is {task.risk_level.value}.")

    def _context(self, task: TaskSpec, text: str) -> DimensionScore:
        score, signals = self._keyword_level("context_size", text)
        if task.task_type == TaskType.EMBEDDED_SYSTEM and len(task.task_subtypes) >= 3:
            score, signals = 3, task.task_subtypes
        elif score < 2 and (("现有" in text and "项目" in text) or ("existing" in text and "project" in text)):
            score, signals = 2, ["existing_project"]
        elif score == 0 and task.available_files:
            score, signals = 1, task.available_files
        elif score == 0 and task.task_type in {TaskType.SOFTWARE_DEVELOPMENT, TaskType.CODE_DEBUGGING}:
            score = 1
        return self._dimension(task, score, signals, f"上下文体量匹配 {score} 级规则。", f"Context volume matches level {score} rules.")

    def _validation(self, task: TaskSpec, text: str) -> DimensionScore:
        score, signals = self._keyword_level("validation", text)
        if task.task_type == TaskType.EMBEDDED_SYSTEM and len(task.task_subtypes) >= 3:
            score, signals = 3, task.task_subtypes
        elif task.task_type in {TaskType.SIMULATION, TaskType.IMAGE_DESIGN} and score < 2:
            score = 2
        elif task.task_type in {TaskType.SOFTWARE_DEVELOPMENT, TaskType.CODE_DEBUGGING} and score < 1:
            score = 1
        if "module_development" in task.task_subtypes and score < 2:
            score = 2
        elif task.task_type in {TaskType.AGENT_DEVELOPMENT, TaskType.REPOSITORY_REFACTORING} and score < 2:
            score = 2
        return self._dimension(task, score, signals, f"验证难度匹配 {score} 级规则。", f"Validation difficulty matches level {score} rules.")
