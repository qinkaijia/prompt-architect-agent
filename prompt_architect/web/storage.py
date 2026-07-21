from __future__ import annotations

import json
import mimetypes
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from prompt_architect.schemas import GenerationResult, ReviewResult
from prompt_architect.web.models import ArtifactMetadata, RunDetail, RunSummary
from prompt_architect.web.paths import AppPaths


SCHEMA_VERSION = 2


class HistoryStore:
    """Small local metadata index; generated artifacts remain regular files."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.paths.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        database_existed = self.paths.database.exists()
        current = 0
        if database_existed:
            with sqlite3.connect(self.paths.database) as connection:
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
                ).fetchone()
                if table:
                    row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
                    current = int(row[0]) if row else 0
        if current and current < SCHEMA_VERSION:
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            shutil.copy2(self.paths.database, self.paths.database.with_suffix(f".db.bak-{stamp}"))

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    sanitized_request TEXT NOT NULL,
                    normalized_goal TEXT NOT NULL,
                    target_agent TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    complexity_score INTEGER NOT NULL,
                    quality_score INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('ready', 'archived')),
                    output_dir TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    PRIMARY KEY (run_id, filename)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sanitized_request TEXT NOT NULL,
                    target_agent TEXT NOT NULL,
                    language TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    clarification_round INTEGER NOT NULL DEFAULT 0,
                    questions_json TEXT NOT NULL DEFAULT '[]',
                    run_id TEXT REFERENCES runs(id),
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_sessions_updated ON agent_sessions(updated_at DESC);
                """
            )
            row = connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()
            if row and row[0]:
                connection.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
            else:
                connection.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def create_agent_session(
        self,
        *,
        session_id: str,
        sanitized_request: str,
        target_agent: str,
        language: str,
        provider: str,
        model_id: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_sessions (
                    id, created_at, updated_at, status, sanitized_request,
                    target_agent, language, provider, model_id
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, sanitized_request, target_agent, language, provider, model_id),
            )

    def update_agent_session(self, session_id: str, **values: object) -> None:
        allowed = {
            "status", "model_id", "clarification_round", "questions_json", "run_id", "last_error"
        }
        selected = {key: value for key, value in values.items() if key in allowed}
        selected["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in selected)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE agent_sessions SET {assignments} WHERE id = ?",
                [*selected.values(), session_id],
            )

    def add_agent_message(self, session_id: str, role: str, content: str) -> None:
        stored = self._excerpt(content, limit=4000)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO agent_messages(session_id, created_at, role, content) VALUES (?, ?, ?, ?)",
                (session_id, datetime.now(UTC).isoformat(), role, stored),
            )

    def add_model_usage(self, session_id: str, *, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO model_usage(
                    session_id, created_at, input_tokens, output_tokens, total_tokens
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, datetime.now(UTC).isoformat(), input_tokens, output_tokens, total_tokens),
            )

    def get_agent_session(self, session_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM agent_sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            usage = connection.execute(
                """
                SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0),
                       COALESCE(SUM(total_tokens), 0)
                FROM model_usage WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return {
            **dict(row),
            "questions": json.loads(row["questions_json"] or "[]"),
            "input_tokens": int(usage[0]),
            "output_tokens": int(usage[1]),
            "total_tokens": int(usage[2]),
        }

    def list_agent_sessions(self, *, limit: int = 30) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM agent_sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [item for row in rows if (item := self.get_agent_session(row["id"])) is not None]

    def fail_incomplete_agent_sessions(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_sessions
                SET status = 'failed', updated_at = ?,
                    last_error = '应用已重启，请重新开始智能生成。'
                WHERE status IN ('pending', 'clarifying', 'generating', 'reviewing', 'repairing')
                """,
                (datetime.now(UTC).isoformat(),),
            )

    def record(self, result: GenerationResult, output_dir: Path, *, run_id: str | None = None) -> str:
        identifier = run_id or str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        title = self._title(result.task.normalized_goal or result.task.sanitized_request)
        stored_request = self._excerpt(result.task.sanitized_request)
        stored_goal = self._excerpt(result.task.normalized_goal)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, created_at, title, sanitized_request, normalized_goal,
                    target_agent, task_type, strategy, complexity_score,
                    quality_score, status, output_dir
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)
                """,
                (
                    identifier,
                    created_at,
                    title,
                    stored_request,
                    stored_goal,
                    result.task.target_agent.value,
                    result.task.task_type.value,
                    result.task.prompt_strategy.value,
                    result.assessment.total_score,
                    result.review.score,
                    str(output_dir.resolve()),
                ),
            )
            self._index_artifacts(connection, identifier, output_dir)
        return identifier

    def list_runs(
        self,
        *,
        query: str = "",
        status: str = "ready",
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[RunSummary], int]:
        clauses: list[str] = []
        values: list[object] = []
        if status in {"ready", "archived"}:
            clauses.append("status = ?")
            values.append(status)
        if query.strip():
            clauses.append("(title LIKE ? OR normalized_goal LIKE ? OR sanitized_request LIKE ?)")
            pattern = f"%{query.strip()}%"
            values.extend([pattern, pattern, pattern])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM runs{where}", values).fetchone()[0])
            rows = connection.execute(
                f"SELECT * FROM runs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return [self._summary(row) for row in rows], total

    def get_run(self, run_id: str) -> RunDetail | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            artifact_rows = connection.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY filename", (run_id,)
            ).fetchall()
        output_dir = self._managed_output(Path(row["output_dir"]))
        analysis = self._load_json(output_dir / "TASK_ANALYSIS.json")
        review_data = self._load_json(output_dir / "REVIEW_REPORT.json")
        summary = self._summary(row)
        return RunDetail(
            **summary.model_dump(),
            sanitized_request=row["sanitized_request"],
            output_dir=str(output_dir),
            task=analysis.get("task", {}),
            complexity=analysis.get("complexity", {}),
            review=ReviewResult.model_validate(review_data),
            artifacts=[
                ArtifactMetadata(
                    filename=item["filename"],
                    media_type=item["media_type"],
                    size=item["size"],
                    download_url=f"/api/v1/runs/{run_id}/artifacts/{item['filename']}",
                )
                for item in artifact_rows
            ],
        )

    def archive(self, run_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET status = 'archived' WHERE id = ?", (run_id,)
            )
            return cursor.rowcount > 0

    def artifact_path(self, run_id: str, filename: str) -> Path | None:
        if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT runs.output_dir, artifacts.filename
                FROM artifacts JOIN runs ON runs.id = artifacts.run_id
                WHERE runs.id = ? AND artifacts.filename = ?
                """,
                (run_id, filename),
            ).fetchone()
        if row is None:
            return None
        output_dir = self._managed_output(Path(row["output_dir"]))
        candidate = (output_dir / row["filename"]).resolve()
        if not candidate.is_relative_to(output_dir) or not candidate.is_file():
            return None
        return candidate

    def reconcile(self) -> int:
        imported = 0
        for candidate in self.paths.runs.iterdir():
            if candidate.is_dir() and self._record_existing(candidate):
                imported += 1
        return imported

    def import_legacy(self, source: Path) -> int:
        resolved = source.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError("The selected history directory does not exist")
        if resolved == self.paths.runs or resolved.is_relative_to(self.paths.runs):
            return self.reconcile()
        imported = 0
        for candidate in resolved.iterdir():
            if not candidate.is_dir() or not (candidate / "TASK_ANALYSIS.json").is_file():
                continue
            target = self._unique_directory(self.paths.runs, candidate.name)
            shutil.copytree(candidate, target)
            if self._record_existing(target):
                imported += 1
            else:
                shutil.rmtree(target)
        return imported

    def _record_existing(self, output_dir: Path) -> bool:
        resolved = self._managed_output(output_dir)
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM runs WHERE output_dir = ?", (str(resolved),)
            ).fetchone()
        if exists:
            return False
        try:
            analysis = self._load_json(resolved / "TASK_ANALYSIS.json")
            review = self._load_json(resolved / "REVIEW_REPORT.json")
            task = analysis["task"]
            complexity = analysis["complexity"]
            identifier = str(uuid4())
            created_at = datetime.fromtimestamp(resolved.stat().st_mtime, UTC).isoformat()
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO runs (
                        id, created_at, title, sanitized_request, normalized_goal,
                        target_agent, task_type, strategy, complexity_score,
                        quality_score, status, output_dir
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)
                    """,
                    (
                        identifier,
                        created_at,
                        self._title(task.get("normalized_goal", "Imported run")),
                        self._excerpt(task.get("sanitized_request", "")),
                        self._excerpt(task.get("normalized_goal", "")),
                        task.get("target_agent", "chat_model"),
                        task.get("task_type", "general"),
                        task.get("prompt_strategy", complexity.get("recommended_strategy", "compact_prompt")),
                        int(complexity.get("total_score", 0)),
                        int(review.get("score", 0)),
                        str(resolved),
                    ),
                )
                self._index_artifacts(connection, identifier, resolved)
            return True
        except (KeyError, OSError, ValueError, json.JSONDecodeError, sqlite3.Error):
            return False

    @staticmethod
    def _index_artifacts(connection: sqlite3.Connection, run_id: str, output_dir: Path) -> None:
        for file_path in sorted(output_dir.iterdir()):
            if not file_path.is_file():
                continue
            media_type = mimetypes.guess_type(file_path.name)[0] or "text/plain"
            connection.execute(
                "INSERT INTO artifacts(run_id, filename, media_type, size) VALUES (?, ?, ?, ?)",
                (run_id, file_path.name, media_type, file_path.stat().st_size),
            )

    def _managed_output(self, output_dir: Path) -> Path:
        resolved = output_dir.resolve()
        root = self.paths.runs.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("Run output is outside the managed data directory")
        return resolved

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _title(value: str) -> str:
        line = " ".join(value.strip().split()) or "Untitled task"
        return line[:72] + ("…" if len(line) > 72 else "")

    @staticmethod
    def _excerpt(value: str, limit: int = 1000) -> str:
        normalized = " ".join(value.strip().split())
        return normalized[:limit] + ("…" if len(normalized) > limit else "")

    @staticmethod
    def _unique_directory(base: Path, name: str) -> Path:
        candidate = base / name
        index = 1
        while candidate.exists():
            candidate = base / f"{name}-{index}"
            index += 1
        return candidate

    @staticmethod
    def _summary(row: sqlite3.Row) -> RunSummary:
        return RunSummary(
            id=row["id"],
            created_at=row["created_at"],
            title=row["title"],
            normalized_goal=row["normalized_goal"],
            target_agent=row["target_agent"],
            task_type=row["task_type"],
            strategy=row["strategy"],
            complexity_score=row["complexity_score"],
            quality_score=row["quality_score"],
            status=row["status"],
        )
