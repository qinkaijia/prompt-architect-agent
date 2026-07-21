from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    database: Path
    runs: Path
    logs: Path

    @classmethod
    def default(cls) -> "AppPaths":
        from platformdirs import user_data_path

        override = os.environ.get("PROMPT_ARCHITECT_DATA_DIR")
        data = (
            Path(override).expanduser()
            if override
            else user_data_path("PromptArchitect", appauthor=False, ensure_exists=True)
        )
        return cls.from_base(data)

    @classmethod
    def from_base(cls, base: Path) -> "AppPaths":
        data = base.resolve()
        paths = cls(
            data_dir=data,
            database=data / "history.db",
            runs=data / "runs",
            logs=data / "logs",
        )
        paths.runs.mkdir(parents=True, exist_ok=True)
        paths.logs.mkdir(parents=True, exist_ok=True)
        return paths
