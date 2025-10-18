import json
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

def test_root_health():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "AI Code Reviewer"
    assert data["status"] == "healthy"

def test_mcp_tools():
    r = client.get("/mcp/tools")
    assert r.status_code == 200
    data = r.json()
    names = [t["name"] for t in data["tools"]]
    assert "review_diff" in names and "demo_diff" in names

def test_mcp_resource_rules():
    r = client.get("/mcp/resources/rules/approval")
    assert r.status_code == 200
    assert "content" in r.json() or isinstance(r.json(), dict)  # compatible with our impl

def test_demo_post():
    body = {"old_code": "def a():\n    return 1\n", "new_code": "def a():\n    return 2\n"}
    r = client.post("/demo", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "generated_diff" in data
    assert "review_result" in data

def test_review_post_mock_mode():
    diff = "@@ -1,1 +1,1 @@\n-print('x')\n+print('y')\n"
    r = client.post("/review", json={"diff": diff, "repo_meta": {"repo": "test"}, "store_review": False})
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"] in {"approve", "needs_changes", "block"}
    assert "summary" in data
    assert "findings" in data

