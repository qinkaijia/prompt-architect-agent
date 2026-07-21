from pathlib import Path

from prompt_architect.service import PromptArchitect


def test_build_matches_generate_without_writing(tmp_path: Path) -> None:
    task = "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。"
    architect = PromptArchitect()
    built = architect.build(task)
    assert built.output_dir is None
    assert not list(tmp_path.iterdir())

    generated = architect.generate(task, output_base=tmp_path)
    assert [item.filename for item in built.artifacts] == [
        item.filename for item in generated.artifacts
    ]
    assert [item.content for item in built.artifacts] == [
        item.content for item in generated.artifacts
    ]
    assert generated.output_dir is not None
