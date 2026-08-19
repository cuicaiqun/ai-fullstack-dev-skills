"""Day1：不依赖外部服务的接口形状测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["day"] == 1
    assert "api" in data["components"]


def test_ask_mock():
    r = client.post(
        "/api/qa/ask",
        json={"question": "什么是RAG？", "session_id": "t1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mock"] is True
    assert data["session_id"] == "t1"
    assert "RAG" in data["answer"] or "rag" in data["answer"].lower() or "问题" in data["answer"]
    assert isinstance(data["sources"], list)


def test_ask_generates_session_id():
    r = client.post("/api/qa/ask", json={"question": "hello"})
    assert r.status_code == 200
    assert r.json()["session_id"]
