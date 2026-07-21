from pathlib import Path

from fastapi.testclient import TestClient

from prompt_architect.web.app import create_app
from prompt_architect.web.paths import AppPaths


SIMPLE_TASK = "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。"


def client_for(tmp_path: Path) -> TestClient:
    return TestClient(create_app(paths=AppPaths.from_base(tmp_path)))


def test_health_and_meta(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    health = client.get("/api/v1/health")
    assert health.json()["status"] == "ok"
    assert health.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in health.headers["content-security-policy"]
    meta = client.get("/api/v1/meta").json()
    assert meta["version"] == "0.2.0"
    assert "codex" in meta["target_agents"]


def test_analyze_exposes_six_explained_dimensions(tmp_path: Path) -> None:
    response = client_for(tmp_path).post("/api/v1/analyze", json={"raw_request": SIMPLE_TASK})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["complexity"]["dimensions"]) == 6
    assert all(item["reason"] for item in payload["complexity"]["dimensions"].values())


def test_generate_persists_and_downloads_run(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    response = client.post("/api/v1/runs", json={"raw_request": SIMPLE_TASK})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["quality_score"] >= 70
    assert any(item["filename"] == "PROMPT.md" for item in run["artifacts"])

    listing = client.get("/api/v1/runs").json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == run["id"]
    prompt = client.get(f"/api/v1/runs/{run['id']}/artifacts/PROMPT.md")
    assert prompt.status_code == 200
    assert "任务目标" in prompt.text
    archive = client.get(f"/api/v1/runs/{run['id']}/download")
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"


def test_vague_generation_returns_structured_422(tmp_path: Path) -> None:
    response = client_for(tmp_path).post(
        "/api/v1/runs", json={"raw_request": "帮我优化一下这个项目。"}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "missing_information"
    assert detail["questions"]
    assert not list((tmp_path / "runs").iterdir())


def test_archive_keeps_files_but_hides_ready_run(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    run = client.post("/api/v1/runs", json={"raw_request": SIMPLE_TASK}).json()
    response = client.post(f"/api/v1/runs/{run['id']}/archive")
    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert client.get("/api/v1/runs?status=ready").json()["total"] == 0
    assert client.get("/api/v1/runs?status=archived").json()["total"] == 1
    assert Path(run["output_dir"]).is_dir()


def test_cross_origin_write_is_rejected(tmp_path: Path) -> None:
    response = client_for(tmp_path).post(
        "/api/v1/analyze",
        headers={"Origin": "https://example.com"},
        json={"raw_request": SIMPLE_TASK},
    )
    assert response.status_code == 403

    wrong_scheme = client_for(tmp_path / "scheme").post(
        "/api/v1/analyze",
        headers={"Origin": "https://testserver"},
        json={"raw_request": SIMPLE_TASK},
    )
    assert wrong_scheme.status_code == 403


def test_raw_secret_never_reaches_database_or_artifacts(tmp_path: Path) -> None:
    secret = "sk-testonly1234567890abcdef"
    client = client_for(tmp_path)
    response = client.post(
        "/api/v1/runs",
        json={
            "raw_request": f"让 Codex 修改配置文件，api_key={secret}，并添加输入检查。",
            "known_context": [f"access_token={secret}"],
            "constraints": [f"password={secret}"],
        },
    )
    assert response.status_code == 201, response.text
    assert secret.encode() not in (tmp_path / "history.db").read_bytes()
    for path in (tmp_path / "runs").rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()


def test_history_search_import_and_missing_artifact_errors(tmp_path: Path) -> None:
    client = client_for(tmp_path / "app")
    run = client.post("/api/v1/runs", json={"raw_request": SIMPLE_TASK}).json()
    assert client.get("/api/v1/runs?query=Python").json()["total"] == 1
    assert client.get("/api/v1/runs?query=不存在").json()["total"] == 0
    assert client.get(f"/api/v1/runs/{run['id']}/artifacts/NOPE.md").status_code == 404
    assert client.get("/api/v1/runs/not-a-run").status_code == 404

    legacy_root = tmp_path / "legacy"
    from prompt_architect.service import PromptArchitect

    PromptArchitect().generate(SIMPLE_TASK, output_base=legacy_root)
    imported = client.post("/api/v1/history/import", json={"path": str(legacy_root)})
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    assert client.get("/api/v1/runs?status=all").json()["total"] == 2


def test_encoded_path_traversal_cannot_read_database(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    run = client.post("/api/v1/runs", json={"raw_request": SIMPLE_TASK}).json()
    response = client.get(
        f"/api/v1/runs/{run['id']}/artifacts/%2E%2E%2F%2E%2E%2Fhistory.db"
    )
    assert response.status_code == 404
