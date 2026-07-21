from pathlib import Path
import sqlite3

from prompt_architect.service import PromptArchitect
from prompt_architect.web.models import GenerationRequest
from prompt_architect.web.paths import AppPaths
from prompt_architect.web.runs import RunService
from prompt_architect.web.storage import HistoryStore


def test_reconcile_restores_missing_index(tmp_path: Path) -> None:
    paths = AppPaths.from_base(tmp_path)
    result = PromptArchitect().generate(
        "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。",
        output_base=paths.runs,
    )
    assert result.output_dir is not None
    store = HistoryStore(paths)
    assert store.reconcile() == 1
    items, total = store.list_runs()
    assert total == 1
    assert items[0].title
    assert store.reconcile() == 0


def test_import_legacy_copies_into_managed_directory(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    PromptArchitect().generate(
        "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。",
        output_base=legacy,
    )
    paths = AppPaths.from_base(tmp_path / "app")
    store = HistoryStore(paths)
    assert store.import_legacy(legacy) == 1
    items, _ = store.list_runs()
    detail = store.get_run(items[0].id)
    assert detail is not None
    assert Path(detail.output_dir).is_relative_to(paths.runs)


def test_artifact_lookup_rejects_unindexed_path(tmp_path: Path) -> None:
    paths = AppPaths.from_base(tmp_path)
    store = HistoryStore(paths)
    assert store.artifact_path("missing", "../history.db") is None


def test_schema_version_and_restart_recovery(tmp_path: Path) -> None:
    paths = AppPaths.from_base(tmp_path)
    first = HistoryStore(paths)
    with sqlite3.connect(paths.database) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == 1

    result = PromptArchitect().generate(
        "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。",
        output_base=paths.runs,
    )
    assert result.output_dir is not None
    restarted = HistoryStore(paths)
    assert restarted.reconcile() == 1
    assert restarted.list_runs(query="Python")[1] == 1


def test_run_service_rolls_back_files_when_indexing_fails(tmp_path: Path, monkeypatch) -> None:
    service = RunService(AppPaths.from_base(tmp_path))

    def fail_record(*args, **kwargs):
        raise sqlite3.OperationalError("simulated index failure")

    monkeypatch.setattr(service.history, "record", fail_record)
    try:
        service.create(
            GenerationRequest(
                raw_request="让 Codex 修改一个 Python 函数，为函数增加输入参数检查。"
            )
        )
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("Expected simulated indexing failure")
    assert not list(service.paths.runs.iterdir())


def test_database_stores_only_bounded_history_excerpt(tmp_path: Path) -> None:
    paths = AppPaths.from_base(tmp_path)
    service = RunService(paths)
    request = "让 Codex 修改一个 Python 函数并增加检查。" + ("背景说明" * 400)
    service.create(GenerationRequest(raw_request=request))
    with sqlite3.connect(paths.database) as connection:
        stored_request, stored_goal = connection.execute(
            "SELECT sanitized_request, normalized_goal FROM runs"
        ).fetchone()
    assert len(stored_request) == 1001
    assert len(stored_goal) == 1001
    assert stored_request.endswith("…")
