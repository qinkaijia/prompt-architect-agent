from prompt_architect.analyzers import RequirementAnalyzer, RuleTaskClassifier
from prompt_architect.schemas import TargetAgent, TaskType


def test_classifier_uses_priority_for_research_hardware_diagram() -> None:
    result = RuleTaskClassifier().classify("生成一张中文科研论文风格的硬件整体连接图")
    assert result.task_type == TaskType.IMAGE_DESIGN
    assert "research_figure" in result.subtypes


def test_target_is_inferred_by_task_type() -> None:
    task = RequirementAnalyzer().analyze("生成一张中文科研论文风格的硬件整体连接图")
    assert task.target_agent == TargetAgent.IMAGE_MODEL
    assert "target_agent" in task.inferred_fields


def test_explicit_target_wins() -> None:
    task = RequirementAnalyzer().analyze("让 Claude Code 修改一个 Python 函数")
    assert task.target_agent == TargetAgent.CLAUDE_CODE
    assert task.field_sources["target_agent"] == "user"


def test_vague_request_is_blocked() -> None:
    task = RequirementAnalyzer().analyze("帮我优化一下这个项目。")
    assert task.has_blockers
    assert "具体优化目标" in task.missing_information


def test_secret_is_redacted_and_raw_is_not_serialized() -> None:
    fake_secret = "sk-" + "testonly1234567890abcdef"
    task = RequirementAnalyzer().analyze(f"让 Codex 写配置，api_key={fake_secret}")
    assert fake_secret not in task.sanitized_request
    assert "raw_request" not in task.model_dump()
    assert any("敏感信息" in item for item in task.forbidden_actions)


def test_available_files_merge_explicit_and_detected_paths() -> None:
    task = RequirementAnalyzer().analyze(
        "修改 src/app.py 并参考 README.md",
        available_files=["config/app.yaml"],
    )
    assert task.available_files == ["config/app.yaml", "src/app.py", "README.md"]
