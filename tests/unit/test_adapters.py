import pytest

from prompt_architect.adapters import AdapterRegistry
from prompt_architect.analyzers import RequirementAnalyzer
from prompt_architect.schemas import Language, TargetAgent


@pytest.mark.parametrize("target", list(TargetAgent))
def test_all_adapters_are_registered(target: TargetAgent) -> None:
    task = RequirementAnalyzer().analyze("完成一个明确的小任务", target_agent=target)
    guidance = AdapterRegistry().get(target).guidance(task)
    assert guidance.role
    assert guidance.execution_rules


def test_codex_adapter_requires_truthful_test_reporting() -> None:
    task = RequirementAnalyzer().analyze("让 Codex 修改函数")
    guidance = AdapterRegistry().get(TargetAgent.CODEX).guidance(task)
    assert any("实际运行" in rule for rule in guidance.execution_rules)
    assert any("不得声称" in rule for rule in guidance.execution_rules)


def test_image_adapter_has_all_visual_dimensions() -> None:
    task = RequirementAnalyzer().analyze("生成科研架构图")
    guidance = AdapterRegistry().get(TargetAgent.IMAGE_MODEL).guidance(task)
    assert len(guidance.required_dimensions) == 10
    assert "画面比例" in guidance.required_dimensions


def test_english_profile_is_used() -> None:
    task = RequirementAnalyzer().analyze("Modify one Python function", language=Language.EN)
    guidance = AdapterRegistry().get(task.target_agent).guidance(task)
    assert guidance.role.startswith("You are")
