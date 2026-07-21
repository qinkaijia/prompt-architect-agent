from pathlib import Path

from prompt_architect.analyzers import RequirementAnalyzer
from prompt_architect.context import ContextManager
from prompt_architect.schemas import ContextCategory


def test_context_is_categorized_without_bulk_reading(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    task = RequirementAnalyzer().analyze(
        "修改 src/app.py 并参考 docs/manual.pdf，忽略 build/generated.py"
    )
    manifest = ContextManager().build(task, base_dir=tmp_path)
    categories = {item.path: item.category for item in manifest.items}
    assert categories["src/app.py"] == ContextCategory.REQUIRED
    assert categories["docs/manual.pdf"] == ContextCategory.REFERENCE_ONLY
    assert categories["build/generated.py"] == ContextCategory.IGNORED
