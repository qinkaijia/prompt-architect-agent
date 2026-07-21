from pathlib import Path

from prompt_architect.evaluators import PromptReviewer
from prompt_architect.schemas import Language, PromptArtifact, PromptStrategy
from prompt_architect.service import PromptArchitect


def test_compact_english_prompt_has_no_empty_background_heading(tmp_path: Path) -> None:
    result = PromptArchitect().generate(
        "Create a concise tutorial explanation",
        language=Language.EN,
        output_base=tmp_path,
    )
    prompt = next(item.content for item in result.artifacts if item.filename == "PROMPT.md")
    assert "# Final Prompt" in prompt
    assert "Background and Current State" not in prompt


def test_project_package_contains_exact_required_prompt_files(tmp_path: Path) -> None:
    request = "让 Codex 设计一个包含传感器、MQTT、Qt、语音、视觉和大模型分析的完整智能工业监测系统。"
    result = PromptArchitect().generate(request, output_base=tmp_path)
    filenames = {artifact.filename for artifact in result.artifacts}
    assert filenames == {
        "PROJECT_BRIEF.md",
        "ARCHITECTURE_PROMPT.md",
        "IMPLEMENTATION_PROMPT.md",
        "TEST_PROMPT.md",
        "REVIEW_PROMPT.md",
        "CONTEXT_MANIFEST.md",
        "ACCEPTANCE_CRITERIA.md",
    }


def test_reviewer_detects_and_repairs_secret() -> None:
    fake_secret = "sk-" + "testonly1234567890abcdef"
    artifact = PromptArtifact(
        filename="PROMPT.md",
        content=f"# 任务目标\n完成任务\n# 输出要求\n代码\n# 验收标准\n测试\napi_key={fake_secret}\n",
    )
    review = PromptReviewer().review_text(artifact.content)
    assert not review.passed
    repaired = PromptReviewer().repair([artifact])
    assert fake_secret not in repaired[0].content


def test_publisher_does_not_overwrite_runs(tmp_path: Path) -> None:
    architect = PromptArchitect()
    first = architect.generate("生成一张科研架构图", output_base=tmp_path)
    second = architect.generate("生成一张科研架构图", output_base=tmp_path)
    assert first.output_dir != second.output_dir
    assert first.output_dir and first.output_dir.exists()
    assert second.output_dir and second.output_dir.exists()
