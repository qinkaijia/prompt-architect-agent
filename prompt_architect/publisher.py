from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from prompt_architect.schemas import GenerationResult


class ArtifactPublisher:
    def publish(self, result: GenerationResult, output_base: Path | None = None) -> Path:
        base = (output_base or Path.cwd() / "outputs").resolve()
        base.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = f"{result.task.task_type.value}-{timestamp}"
        target = self._unique_directory(base, stem)
        temporary = base / f".{target.name}.tmp"
        counter = 1
        while temporary.exists():
            temporary = base / f".{target.name}.tmp-{counter}"
            counter += 1
        temporary.mkdir()
        try:
            for artifact in result.artifacts:
                destination = temporary / artifact.filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(artifact.content, encoding="utf-8")
            analysis_payload = {
                "task": result.task.model_dump(mode="json"),
                "complexity": result.assessment.model_dump(mode="json"),
            }
            (temporary / "TASK_ANALYSIS.json").write_text(
                json.dumps(analysis_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (temporary / "REVIEW_REPORT.json").write_text(
                json.dumps(result.review.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.rename(target)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        return target

    @staticmethod
    def _unique_directory(base: Path, stem: str) -> Path:
        candidate = base / stem
        counter = 1
        while candidate.exists():
            candidate = base / f"{stem}-{counter}"
            counter += 1
        return candidate
