from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from prompt_architect import __version__
from prompt_architect.schemas import Language, PromptStrategy, TargetAgent, TaskType
from prompt_architect.service import (
    MissingInformationError,
    QualityGateError,
    StrategyBlockedError,
)
from prompt_architect.web.models import (
    AnalysisResponse,
    ApiError,
    GenerationRequest,
    ImportRequest,
    ImportResponse,
    RunDetail,
    RunListResponse,
)
from prompt_architect.web.paths import AppPaths
from prompt_architect.web.runs import RunService


class SameOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            host = request.headers.get("host", "")
            if (
                parsed.netloc.casefold() != host.casefold()
                or parsed.scheme != request.url.scheme
            ):
                return Response(status_code=403, content="Cross-origin requests are not allowed")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def _api_error(status: int, error: ApiError) -> HTTPException:
    return HTTPException(status_code=status, detail=error.model_dump(mode="json"))


def create_app(*, paths: AppPaths | None = None, desktop: bool = False) -> FastAPI:
    resolved_paths = paths or AppPaths.default()
    runs = RunService(resolved_paths)
    app = FastAPI(
        title="Prompt Architect Agent",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.paths = resolved_paths
    app.state.runs = runs
    app.state.desktop = desktop
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/meta")
    def meta() -> dict:
        return {
            "version": __version__,
            "desktop": desktop,
            "target_agents": [item.value for item in TargetAgent],
            "languages": [item.value for item in Language],
            "task_types": [item.value for item in TaskType],
            "strategies": [item.value for item in PromptStrategy],
        }

    @app.post("/api/v1/analyze", response_model=AnalysisResponse)
    def analyze(payload: GenerationRequest) -> AnalysisResponse:
        task, complexity, routing = runs.architect.analyze(**payload.service_kwargs())
        return AnalysisResponse(
            task=task,
            complexity=complexity,
            routing=routing,
            blockers=task.blocking_questions,
        )

    @app.post("/api/v1/runs", response_model=RunDetail, status_code=201)
    def create_run(payload: GenerationRequest) -> RunDetail:
        try:
            return runs.create(payload)
        except MissingInformationError as exc:
            raise _api_error(
                422,
                ApiError(
                    code="missing_information",
                    message="请补充关键信息后再生成。",
                    questions=exc.task.blocking_questions,
                    context={"task": exc.task.model_dump(mode="json")},
                ),
            ) from exc
        except StrategyBlockedError as exc:
            raise _api_error(
                409,
                ApiError(
                    code="strategy_blocked",
                    message=exc.decision.reason,
                    context={"routing": exc.decision.model_dump(mode="json")},
                ),
            ) from exc
        except QualityGateError as exc:
            raise _api_error(
                409,
                ApiError(
                    code="quality_gate_failed",
                    message="生成内容未通过质量检查。",
                    context={"review": exc.review.model_dump(mode="json")},
                ),
            ) from exc

    @app.get("/api/v1/runs", response_model=RunListResponse)
    def list_runs(
        query: str = "",
        status: str = Query(default="ready", pattern="^(ready|archived|all)$"),
        limit: int = Query(default=30, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> RunListResponse:
        return runs.list(query=query, status=status, limit=limit, offset=offset)

    @app.get("/api/v1/runs/{run_id}", response_model=RunDetail)
    def get_run(run_id: str) -> RunDetail:
        detail = runs.get(run_id)
        if detail is None:
            raise _api_error(404, ApiError(code="run_not_found", message="未找到该生成记录。"))
        return detail

    @app.get("/api/v1/runs/{run_id}/artifacts/{filename}")
    def get_artifact(run_id: str, filename: str, download: bool = False):
        path = runs.artifact(run_id, filename)
        if path is None:
            raise _api_error(404, ApiError(code="artifact_not_found", message="未找到该文件。"))
        if download:
            return FileResponse(path, media_type="application/octet-stream", filename=path.name)
        media_type = "application/json" if path.suffix.casefold() == ".json" else "text/markdown"
        return Response(path.read_text(encoding="utf-8"), media_type=media_type)

    @app.get("/api/v1/runs/{run_id}/download")
    def download_run(run_id: str) -> Response:
        payload = runs.zip_bytes(run_id)
        if payload is None:
            raise _api_error(404, ApiError(code="run_not_found", message="未找到该生成记录。"))
        return Response(
            payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="prompt-architect-{run_id}.zip"'},
        )

    @app.post("/api/v1/runs/{run_id}/archive", response_model=RunDetail)
    def archive_run(run_id: str) -> RunDetail:
        detail = runs.archive(run_id)
        if detail is None:
            raise _api_error(404, ApiError(code="run_not_found", message="未找到该生成记录。"))
        return detail

    @app.post("/api/v1/history/import", response_model=ImportResponse)
    def import_history(payload: ImportRequest) -> ImportResponse:
        try:
            imported = runs.history.import_legacy(Path(payload.path))
        except ValueError as exc:
            raise _api_error(422, ApiError(code="invalid_history_path", message=str(exc))) from exc
        return ImportResponse(imported=imported)

    static_root = Path(str(files("prompt_architect.web").joinpath("static")))
    if static_root.is_dir() and (static_root / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def frontend_missing() -> str:
            return (
                "<main style='font-family:system-ui;max-width:680px;margin:80px auto'>"
                "<h1>Prompt Architect Agent</h1>"
                "<p>前端资源尚未构建。请在 frontend 目录运行 npm run build。</p>"
                "</main>"
            )
    return app
