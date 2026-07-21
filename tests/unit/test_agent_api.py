from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from prompt_architect.llm.credentials import CredentialStore
from prompt_architect.llm.deepseek import DeepSeekProvider
from prompt_architect.web.app import create_app
from prompt_architect.web.paths import AppPaths


class MemoryKeyring:
    def __init__(self) -> None:
        self.value: str | None = None

    def get_password(self, _service: str, _username: str):
        return self.value

    def set_password(self, _service: str, _username: str, value: str) -> None:
        self.value = value

    def delete_password(self, _service: str, _username: str) -> None:
        self.value = None


def model_response(content: dict, *, tokens: int = 10) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": tokens - 3, "completion_tokens": 3, "total_tokens": tokens},
        },
    )


def analysis_payload(*, questions: list[str] | None = None) -> dict:
    return {
        "normalized_goal": "让 Codex 修改一个 Python 函数并增加输入检查",
        "task_type": "software_development",
        "task_subtypes": ["function_change"],
        "target_agent": "codex",
        "deliverables": ["修改后的函数"],
        "known_context": ["Python 项目"],
        "constraints": ["最小修改"],
        "forbidden_actions": ["不得伪造测试结果"],
        "tools": ["pytest"],
        "missing_information": ["函数路径"] if questions else [],
        "acceptance_criteria": ["输入无效时返回清晰错误"],
        "risk_level": "low",
        "dimensions": {
            name: {"score": 1, "reason": f"{name} 可控"}
            for name in ["scope", "dependencies", "ambiguity", "risk", "context_size", "validation_difficulty"]
        },
        "questions": questions or [],
        "reason": "中等规模且边界明确。",
    }


def client_for(tmp_path: Path, *, ask_once: bool = False) -> tuple[TestClient, MemoryKeyring]:
    keyring = MemoryKeyring()
    analysis_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal analysis_calls
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": "deepseek-test", "owned_by": "deepseek"}]})
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        if "需求分析器" in system:
            analysis_calls += 1
            return model_response(analysis_payload(questions=["需要修改哪个函数？"] if ask_once and analysis_calls == 1 else []))
        if "资深提示词架构师" in system:
            return model_response({"files": [{"filename": "PROMPT.md", "content": "# 任务目标\n修改函数并增加输入检查。\n\n# 输出产物\n- 修改后的函数\n\n# 验收标准\n- 无效输入返回清晰错误\n\n不得伪造测试结果。"}]})
        if "质量审查员" in system:
            return model_response({"passed": True, "score": 96, "issues": [], "suggestions": []})
        raise AssertionError(system)

    provider = DeepSeekProvider(CredentialStore(keyring), transport=httpx.MockTransport(handler))
    app = create_app(paths=AppPaths.from_base(tmp_path), provider=provider)
    return TestClient(app), keyring


def test_friendly_credential_setup_and_agent_generation(tmp_path: Path) -> None:
    client, keyring = client_for(tmp_path)
    secret = "new-local-test-secret"
    status = client.get("/api/v1/providers/deepseek").json()
    assert status["configured"] is False
    invalid_value = "x" * 513
    invalid = client.put("/api/v1/providers/deepseek/credential", json={"api_key": invalid_value})
    assert invalid.status_code == 422
    assert invalid_value not in invalid.text

    connected = client.put(
        "/api/v1/providers/deepseek/credential", json={"api_key": f"  {secret}  "}
    )
    assert connected.status_code == 200
    assert connected.json()["key_hint"].endswith(secret[-4:])
    assert secret not in connected.text
    assert keyring.value == secret

    session = client.post(
        "/api/v1/agent/sessions",
        json={"raw_request": "让 Codex 修改一个 Python 函数，为函数增加输入参数检查。"},
    ).json()
    streamed = client.post(f"/api/v1/agent/sessions/{session['id']}/turns", json={"answers": []})
    assert streamed.status_code == 200
    assert "analysis.completed" in streamed.text
    assert "run.published" in streamed.text

    detail = client.get(f"/api/v1/agent/sessions/{session['id']}").json()
    assert detail["status"] == "completed"
    assert detail["model_id"] == "deepseek-test"
    assert detail["total_tokens"] > 0
    assert any(item["filename"] == "PROMPT.md" for item in detail["run"]["artifacts"])
    assert secret.encode() not in (tmp_path / "history.db").read_bytes()
    for candidate in tmp_path.rglob("*"):
        if candidate.is_file():
            assert secret.encode() not in candidate.read_bytes()

    removed = client.delete("/api/v1/providers/deepseek/credential")
    assert removed.status_code == 200
    assert removed.json()["configured"] is False
    assert keyring.value is None


def test_agent_pauses_for_targeted_question_and_resumes(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path, ask_once=True)
    client.put("/api/v1/providers/deepseek/credential", json={"api_key": "another-test-secret"})
    session = client.post("/api/v1/agent/sessions", json={"raw_request": "请修改函数。"}).json()
    first = client.post(f"/api/v1/agent/sessions/{session['id']}/turns", json={"answers": []})
    assert "questions.required" in first.text
    waiting = client.get(f"/api/v1/agent/sessions/{session['id']}").json()
    assert waiting["status"] == "clarifying"
    assert waiting["questions"] == ["需要修改哪个函数？"]

    second = client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"answers": ["src/example.py 中的 parse_input 函数"]},
    )
    assert "run.published" in second.text
    assert client.get(f"/api/v1/agent/sessions/{session['id']}").json()["status"] == "completed"


def test_browser_upload_is_scoped_and_rejects_unsupported_type(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    accepted = client.post(
        "/api/v1/context/uploads", files=[("files", ("example.py", b"print('ok')", "text/plain"))]
    )
    assert accepted.status_code == 200
    assert accepted.json()["files"][0]["name"] == "example.py"
    rejected = client.post(
        "/api/v1/context/uploads", files=[("files", ("malware.exe", b"MZ", "application/octet-stream"))]
    )
    assert rejected.status_code == 422
