from prompt_architect.analyzers import ComplexityScorer, RequirementAnalyzer
from prompt_architect.routing import StrategyRouter
from prompt_architect.schemas import PromptStrategy


def test_staged_task_downgrades_when_staging_disabled() -> None:
    task = RequirementAnalyzer().analyze(
        "让 Codex 在现有 Python 项目中开发一个可切换百度和讯飞的 ASR 模块。",
        allow_staged=False,
    )
    assessment = ComplexityScorer().score(task)
    decision = StrategyRouter().route(task, assessment)
    assert assessment.recommended_strategy == PromptStrategy.STAGED
    assert decision.selected_strategy == PromptStrategy.STRUCTURED
    assert decision.warnings


def test_project_task_blocks_when_staging_disabled() -> None:
    request = "让 Codex 设计一个包含传感器、MQTT、Qt、语音、视觉和大模型分析的完整智能工业监测系统。"
    task = RequirementAnalyzer().analyze(request, allow_staged=False)
    assessment = ComplexityScorer().score(task)
    decision = StrategyRouter().route(task, assessment)
    assert assessment.recommended_strategy == PromptStrategy.PROJECT
    assert decision.blocked
    assert decision.selected_strategy is None
