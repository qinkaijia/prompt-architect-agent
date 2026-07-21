from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

from prompt_architect.publisher import ArtifactPublisher
from prompt_architect.schemas import GenerationResult
from prompt_architect.service import PromptArchitect
from prompt_architect.web.models import GenerationRequest, RunDetail, RunListResponse
from prompt_architect.web.paths import AppPaths
from prompt_architect.web.storage import HistoryStore


class RunService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.architect = PromptArchitect()
        self.publisher = ArtifactPublisher()
        self.history = HistoryStore(paths)
        self.history.reconcile()

    def create(self, request: GenerationRequest) -> RunDetail:
        result = self.architect.build(**request.service_kwargs())
        return self.publish_result(result)

    def publish_result(self, result: GenerationResult) -> RunDetail:
        output_dir = self.publisher.publish(result, self.paths.runs)
        try:
            run_id = self.history.record(result, output_dir)
        except Exception:
            # Publishing is atomic on disk. If the metadata transaction fails,
            # roll back the newly-created run so callers never observe a partial run.
            shutil.rmtree(output_dir, ignore_errors=True)
            raise
        detail = self.history.get_run(run_id)
        if detail is None:
            raise RuntimeError("Generated run could not be indexed")
        return detail

    def list(self, *, query: str, status: str, limit: int, offset: int) -> RunListResponse:
        items, total = self.history.list_runs(
            query=query, status=status, limit=limit, offset=offset
        )
        return RunListResponse(items=items, total=total, limit=limit, offset=offset)

    def get(self, run_id: str) -> RunDetail | None:
        return self.history.get_run(run_id)

    def archive(self, run_id: str) -> RunDetail | None:
        if not self.history.archive(run_id):
            return None
        return self.history.get_run(run_id)

    def artifact(self, run_id: str, filename: str) -> Path | None:
        return self.history.artifact_path(run_id, filename)

    def zip_bytes(self, run_id: str) -> bytes | None:
        detail = self.get(run_id)
        if detail is None:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in detail.artifacts:
                path = self.artifact(run_id, item.filename)
                if path is not None:
                    archive.write(path, arcname=item.filename)
        return buffer.getvalue()
