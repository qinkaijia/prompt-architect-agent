import json
from pathlib import Path

from typer.testing import CliRunner

from prompt_architect.cli import app


runner = CliRunner()


def test_generate_noninteractive_writes_artifacts(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["generate", "--task", "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。", "--output", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "PROMPT.md").exists()
    assert (run_dirs[0] / "TASK_ANALYSIS.json").exists()


def test_vague_noninteractive_request_exits_without_output(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["generate", "--task", "帮我优化一下这个项目。", "--output", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert not tmp_path.exists() or not list(tmp_path.iterdir())


def test_analyze_json_never_contains_raw_secret() -> None:
    fake_secret = "sk-" + "testonly1234567890abcdef"
    result = runner.invoke(
        app,
        ["analyze", "--task", f"写配置 api_key={fake_secret}", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert fake_secret not in result.output
    payload = json.loads(result.output)
    assert "raw_request" not in payload["task"]
    assert "[REDACTED]" in result.output


def test_review_command_returns_nonzero_for_incomplete_prompt(tmp_path: Path) -> None:
    prompt = tmp_path / "bad.md"
    prompt.write_text("随便做一下", encoding="utf-8")
    result = runner.invoke(app, ["review", str(prompt)])
    assert result.exit_code == 2
