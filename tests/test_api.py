"""Tests for the FastAPI layer."""

from fastapi.testclient import TestClient

from src.api.main import create_app


def _client(repository, tmp_path):
    return TestClient(create_app(repo=repository, traces_dir=tmp_path / "traces"))


def test_health(repository, tmp_path):
    response = _client(repository, tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_redirects_to_docs(repository, tmp_path):
    client = _client(repository, tmp_path)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
    assert client.get("/").url.path == "/docs"


def test_asset_and_work_orders(repository, tmp_path):
    client = _client(repository, tmp_path)

    response = client.get("/assets/A001")
    assert response.status_code == 200
    assert response.json()["asset_id"] == "A001"
    assert client.get("/assets/NOPE").status_code == 404

    response = client.get("/work-orders", params={"asset_id": "A001", "days": 30, "limit": 10})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_meter_summary(repository, tmp_path):
    response = _client(repository, tmp_path).get(
        "/meter-summary", params={"asset_id": "A001", "days": 30}
    )
    assert response.status_code == 200
    assert "signals" in response.json()


def test_agent_query_and_approval_flow(repository, tmp_path):
    client = _client(repository, tmp_path)
    response = client.post("/agent/query", json={"question": "A001 stopped this week."})
    assert response.status_code == 200
    data = response.json()
    assert data["hypotheses"][0]["cause"] == "Lubrication degradation"
    request_id = data["request_id"]

    approve = client.post(f"/actions/{request_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"
    assert approve.json()["approved_by"] == "api"
    assert approve.json()["approved_at"] is not None

    assert client.post("/actions/nope/approve").status_code == 404

    trace = client.get(f"/traces/{request_id}")
    assert trace.status_code == 200
    assert trace.json()["request_id"] == request_id


def test_agent_query_rejects_invalid_request_id(repository, tmp_path):
    client = _client(repository, tmp_path)
    response = client.post(
        "/agent/query", json={"question": "A001 stopped", "request_id": "../evil"}
    )
    assert response.status_code == 400


def test_trace_route_rejects_reserved_request_id(repository, tmp_path):
    client = _client(repository, tmp_path)
    assert client.get("/traces/CON").status_code == 400


def test_action_routes_reject_reserved_action_id(repository, tmp_path):
    client = _client(repository, tmp_path)
    assert client.post("/actions/CON/approve").status_code == 400
    assert client.post("/actions/NUL/reject").status_code == 400
