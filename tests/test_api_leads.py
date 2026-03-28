from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.server import create_app


def _read_ndjson(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submit_lead_writes_log(tmp_path: Path):
    log_path = tmp_path / "leads.ndjson"
    app = create_app(lead_log_path=log_path)
    client = TestClient(app)

    payload = {
        "name": " 张三 ",
        "email": "zhangsan@example.com",
        "company": " Demo Team ",
        "goal": " 我们想做面向新手的杭麻陪练应用 ",
    }
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["lead_id"]) == 12

    assert log_path.exists()
    logs = _read_ndjson(log_path)
    assert len(logs) == 1
    assert logs[0]["name"] == "张三"
    assert logs[0]["company"] == "Demo Team"
    assert logs[0]["goal"] == "我们想做面向新手的杭麻陪练应用"


def test_submit_lead_rejects_invalid_email(tmp_path: Path):
    app = create_app(lead_log_path=tmp_path / "leads.ndjson")
    client = TestClient(app)
    payload = {
        "name": "李四",
        "email": "not-an-email",
        "company": "",
        "goal": "test",
    }
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 422
    assert "邮箱格式无效" in response.text

