import pytest

from prompt_architect.schemas import PromptStrategy, TargetAgent, TaskType
from prompt_architect.service import MissingInformationError, PromptArchitect


@pytest.mark.parametrize(
    ("task_request", "expected_type", "expected_strategies"),
    [
        (
            "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。",
            TaskType.SOFTWARE_DEVELOPMENT,
            {PromptStrategy.COMPACT, PromptStrategy.STRUCTURED},
        ),
        (
            "让 Codex 在现有 Python 项目中开发一个可切换百度和讯飞的 ASR 模块。",
            TaskType.SOFTWARE_DEVELOPMENT,
            {PromptStrategy.STRUCTURED, PromptStrategy.STAGED},
        ),
        (
            "让 Codex 设计一个包含传感器、MQTT、Qt、语音、视觉和大模型分析的完整智能工业监测系统。",
            TaskType.EMBEDDED_SYSTEM,
            {PromptStrategy.PROJECT},
        ),
    ],
)
def test_development_scenarios(task_request, expected_type, expected_strategies) -> None:
    task, assessment, _ = PromptArchitect().analyze(task_request)
    assert task.task_type == expected_type
    assert assessment.recommended_strategy in expected_strategies


def test_research_image_scenario_contains_visual_spec(tmp_path) -> None:
    result = PromptArchitect().generate(
        "生成一张中文科研论文风格的硬件整体连接图。", output_base=tmp_path
    )
    assert result.task.target_agent == TargetAgent.IMAGE_MODEL
    prompt = next(item.content for item in result.artifacts if item.filename == "PROMPT.md")
    for term in ("画面比例", "布局方式", "模块内容", "风格", "禁止元素"):
        assert term in prompt


def test_ambiguous_scenario_does_not_publish(tmp_path) -> None:
    with pytest.raises(MissingInformationError):
        PromptArchitect().generate("帮我优化一下这个项目。", output_base=tmp_path)
    assert not list(tmp_path.iterdir())
