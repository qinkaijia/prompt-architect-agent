from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

import json

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from prompt_architect import __version__
from prompt_architect.llm.context import ContextGrantError, ContextGrantStore, MAX_PDF_BYTES
from prompt_architect.llm.credentials import CredentialUnavailableError
from prompt_architect.llm.deepseek import DeepSeekProvider, ProviderError
from prompt_architect.schemas import Language, PromptStrategy, TargetAgent, TaskType
from prompt_architect.service import (
    MissingInformationError,
    QualityGateError,
    StrategyBlockedError,
)
from prompt_architect.web.models import (
    AnalysisResponse,
    AgentSessionCreate,
    AgentSessionDetail,
    AgentSessionSummary,
    AgentTurnRequest,
    ApiError,
    ContextGrantResponse,
    CredentialRequest,
    DesktopGrantRequest,
    GenerationRequest,
    ImportRequest,
    ImportResponse,
    ModelSettingRequest,
    RunDetail,
    RunListResponse,
)
from prompt_architect.web.paths import AppPaths
from prompt_architect.web.agent import AgentService
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


def create_app(
    *,
    paths: AppPaths | None = None,
    desktop: bool = False,
    provider: DeepSeekProvider | None = None,
) -> FastAPI:
    resolved_paths = paths or AppPaths.default()
    runs = RunService(resolved_paths)
    deepseek = provider or DeepSeekProvider()
    grants = ContextGrantStore(resolved_paths.temp)
    agents = AgentService(runs, deepseek, grants)
    app = FastAPI(
        title="Prompt Architect Agent",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.paths = resolved_paths
    app.state.runs = runs
    app.state.desktop = desktop
    app.state.provider = deepseek
    app.state.grants = grants
    app.state.agents = agents
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

    @app.get("/api/v1/providers/deepseek")
    async def provider_status():
        default_model = runs.history.get_setting("deepseek.default_model", "auto")
        return await deepseek.status(default_model=default_model)

    @app.put("/api/v1/providers/deepseek/credential")
    async def save_credential(payload: CredentialRequest):
        candidate = payload.api_key.strip()
        if not candidate or len(candidate) > 512:
            raise _api_error(422, ApiError(code="invalid_credential", message="API Key 格式无效。"))
        try:
            models = await deepseek.test_key(candidate)
            deepseek.credentials.set(candidate)
        except ProviderError as exc:
            raise _api_error(exc.status_code or 503, ApiError(code=exc.code, message=str(exc))) from exc
        except (CredentialUnavailableError, ValueError) as exc:
            raise _api_error(409, ApiError(code="credential_store_unavailable", message=str(exc))) from exc
        status = await deepseek.status(default_model=runs.history.get_setting("deepseek.default_model", "auto"))
        return status.model_copy(update={"connected": True, "models": models, "message": "DeepSeek 已连接。"})

    @app.delete("/api/v1/providers/deepseek/credential")
    async def delete_credential():
        try:
            deepseek.credentials.delete()
        except CredentialUnavailableError as exc:
            raise _api_error(409, ApiError(code="credential_managed_externally", message=str(exc))) from exc
        runs.history.set_setting("deepseek.default_model", "auto")
        return await deepseek.status(default_model="auto")

    @app.post("/api/v1/providers/deepseek/test")
    async def test_provider():
        try:
            models = await deepseek.list_models()
        except ProviderError as exc:
            raise _api_error(exc.status_code or 503, ApiError(code=exc.code, message=str(exc))) from exc
        status = await deepseek.status(default_model=runs.history.get_setting("deepseek.default_model", "auto"))
        return status.model_copy(update={"connected": True, "models": models, "message": "DeepSeek 已连接。"})

    @app.get("/api/v1/providers/deepseek/models")
    async def provider_models():
        try:
            return {"items": await deepseek.list_models()}
        except ProviderError as exc:
            raise _api_error(exc.status_code or 503, ApiError(code=exc.code, message=str(exc))) from exc

    @app.put("/api/v1/settings/default-model")
    async def set_default_model(payload: ModelSettingRequest):
        if payload.model_id != "auto":
            try:
                ids = {item.id for item in await deepseek.list_models()}
            except ProviderError as exc:
                raise _api_error(exc.status_code or 503, ApiError(code=exc.code, message=str(exc))) from exc
            if payload.model_id not in ids:
                raise _api_error(422, ApiError(code="model_unavailable", message="所选模型当前不可用。"))
        runs.history.set_setting("deepseek.default_model", payload.model_id)
        return {"model_id": payload.model_id}

    @app.post("/api/v1/context/grants", response_model=ContextGrantResponse)
    async def grant_desktop_context(payload: DesktopGrantRequest):
        if not desktop:
            raise _api_error(403, ApiError(code="desktop_only", message="只有桌面模式可以授权本地路径。"))
        try:
            grant = grants.grant_desktop(payload.paths)
        except ContextGrantError as exc:
            raise _api_error(422, ApiError(code="invalid_context", message=str(exc))) from exc
        return ContextGrantResponse.model_validate(grants.public(grant))

    @app.post("/api/v1/context/uploads", response_model=ContextGrantResponse)
    async def upload_context(files_payload: list[UploadFile] = File(alias="files")):
        if len(files_payload) > 10:
            raise _api_error(422, ApiError(code="too_many_files", message="一次最多上传 10 个文件。"))
        uploads: list[tuple[str, bytes]] = []
        for item in files_payload:
            content = await item.read(MAX_PDF_BYTES + 1)
            uploads.append((item.filename or "file", content))
        try:
            grant = grants.grant_uploads(uploads)
        except ContextGrantError as exc:
            raise _api_error(422, ApiError(code="invalid_context", message=str(exc))) from exc
        return ContextGrantResponse.model_validate(grants.public(grant))

    @app.post("/api/v1/agent/sessions", response_model=AgentSessionDetail, status_code=201)
    async def create_agent_session(payload: AgentSessionCreate):
        if not payload.offline_rules and not deepseek.credentials.get().value:
            raise _api_error(401, ApiError(code="not_configured", message="请先设置 DeepSeek API Key。"))
        try:
            return agents.create(payload)
        except ContextGrantError as exc:
            raise _api_error(422, ApiError(code="invalid_context", message=str(exc))) from exc

    @app.get("/api/v1/agent/sessions", response_model=list[AgentSessionSummary])
    async def list_agent_sessions():
        return agents.list()

    @app.get("/api/v1/agent/sessions/{session_id}", response_model=AgentSessionDetail)
    async def get_agent_session(session_id: str):
        detail = agents.get(session_id)
        if detail is None:
            raise _api_error(404, ApiError(code="session_not_found", message="未找到该智能生成会话。"))
        return detail

    @app.post("/api/v1/agent/sessions/{session_id}/turns")
    async def agent_turn(session_id: str, payload: AgentTurnRequest):
        if agents.get(session_id) is None:
            raise _api_error(404, ApiError(code="session_not_found", message="未找到该智能生成会话。"))

        async def stream():
            try:
                async for item in agents.stream_turn(session_id, payload.answers):
                    yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
            except (KeyError, ValueError) as exc:
                yield f"event: failed\ndata: {json.dumps({'code': 'invalid_turn', 'message': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/agent/sessions/{session_id}/cancel")
    async def cancel_agent_session(session_id: str):
        if not agents.cancel(session_id):
            raise _api_error(404, ApiError(code="session_not_found", message="该会话不存在或已经结束。"))
        return {"cancelled": True}

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
    ModelSettingRequest,
