import json
import uuid

import httpx
from fastapi.testclient import TestClient

from src.calculator_agent import app as calculator_app
from src.calculator_tool_server import app as tool_app
from src.explainer_agent import app as explainer_app
from src.explainer_agent import select_calculator

RESULT = "计算结果: 3 + 5 = 8（MCP工具返回: 8）"


def rpc(method: str, params: dict) -> dict:
    return {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}


def message(text: str) -> dict:
    return {"id": str(uuid.uuid4()), "message": {"role": "user", "parts": [{"type": "text", "text": text}]}}


def parse_sse(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def wait_until_terminal(client: TestClient, task_id: str) -> dict:
    last = None
    for _ in range(30):
        last = client.post("/", json=rpc("tasks/get", {"id": task_id})).json()
        if last["result"]["status"]["state"] in ("completed", "failed"):
            return last
    raise AssertionError(last)


def test_mcp_lists_and_calls_tools():
    client = TestClient(tool_app)
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert {tool["name"] for tool in listed.json()["result"]["tools"]} == {"add", "multiply", "power"}
    called = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 3, "b": 5}}})
    assert called.json()["result"]["structuredContent"]["value"] == 8


def test_agent_card_is_discoverable():
    client = TestClient(calculator_app)
    response = client.get("/.well-known/agent.json")
    assert response.json()["name"] == "MathAssistantAgent"
    assert response.json()["skills"][0]["id"] == "math-calculator"
    assert response.json()["capabilities"]["streaming"] is True


def test_explainer_card_has_no_calculation_skill():
    card = TestClient(explainer_app).get("/.well-known/agent.json").json()
    assert card["name"] == "ExplainerAgent"
    assert "math-calculator" not in {skill["id"] for skill in card["skills"]}


def test_select_calculator_by_published_skill():
    chosen = select_calculator([
        ("http://127.0.0.1:8002", {"skills": [{"id": "explain-task"}]}),
        ("http://127.0.0.1:8001", {"skills": [{"id": "math-calculator"}]}),
    ])
    assert chosen is not None
    assert chosen[0] == "http://127.0.0.1:8001"
    assert select_calculator([("http://127.0.0.1:8002", {"skills": [{"id": "explain-task"}]})]) is None


def test_calculator_send_returns_working_then_get_reads_artifact(monkeypatch):
    async def fake_call(name, arguments):
        assert name == "add"
        assert arguments == {"a": 3.0, "b": 5.0}
        return 8.0

    monkeypatch.setattr("src.calculator_agent.call_mcp_tool", fake_call)
    client = TestClient(calculator_app)
    sent = client.post("/", json=rpc("tasks/send", message("计算3+5"))).json()
    assert sent["result"]["status"]["state"] == "working"
    finished = wait_until_terminal(client, sent["result"]["id"])
    assert finished["result"]["status"]["state"] == "completed"
    assert finished["result"]["artifacts"][0]["parts"][0]["text"] == RESULT


def test_calculator_subscribe_streams_status_then_artifact(monkeypatch):
    async def fake_call(name, arguments):
        return 8.0

    monkeypatch.setattr("src.calculator_agent.call_mcp_tool", fake_call)
    client = TestClient(calculator_app)
    response = client.post("/", json=rpc("tasks/sendSubscribe", message("计算3+5")))
    assert response.headers["content-type"].startswith("text/event-stream")
    kinds = []
    for event in parse_sse(response.text):
        result = event["result"]
        if "artifact" in result:
            kinds.append("artifact")
            assert result["artifact"]["parts"][0]["text"] == RESULT
        else:
            kinds.append("status")
            if result.get("final"):
                assert result["status"]["state"] == "completed"
    artifact_at = kinds.index("artifact")
    assert artifact_at > 0
    assert kinds[:artifact_at] == ["status"] * artifact_at
    assert kinds[-1] == "status"


def test_unknown_task_get_returns_error():
    for app in (calculator_app, explainer_app):
        missing = TestClient(app).post("/", json=rpc("tasks/get", {"id": "missing-task"})).json()
        assert missing["error"]["code"] == -32001


def install_peer(monkeypatch, skill: str, state: str = "completed"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/agent.json":
            return httpx.Response(200, json={"name": "Peer", "skills": [{"id": skill}]})
        body = json.loads(request.content)
        if body["method"] == "tasks/send":
            assert body["params"]["message"]["parts"][0]["text"] == "计算3+5"
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"id": "calc-task", "status": {"state": "working"}},
            })
        result = {"id": "calc-task", "status": {"state": state}}
        if state == "completed":
            result["artifacts"] = [{"parts": [{"type": "text", "text": RESULT}]}]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    transport = httpx.MockTransport(handler)

    def factory():
        return httpx.AsyncClient(transport=transport, timeout=30)

    monkeypatch.setattr("src.explainer_agent.client_factory", factory)


def test_explainer_delegates_and_returns_calculator_text(monkeypatch):
    install_peer(monkeypatch, "math-calculator")
    client = TestClient(explainer_app)
    sent = client.post("/", json=rpc("tasks/send", message("计算3+5"))).json()
    assert sent["result"]["status"]["state"] == "working"
    finished = wait_until_terminal(client, sent["result"]["id"])
    assert finished["result"]["status"]["state"] == "completed"
    assert finished["result"]["artifacts"][0]["parts"][0]["text"] == RESULT


def test_explainer_fails_when_plaza_has_no_calculator(monkeypatch):
    install_peer(monkeypatch, "explain-task")
    client = TestClient(explainer_app)
    sent = client.post("/", json=rpc("tasks/send", message("计算3+5"))).json()
    finished = wait_until_terminal(client, sent["result"]["id"])
    assert finished["result"]["status"]["state"] == "failed"
    assert "“技能广场”上没有会计算的 Agent" in finished["result"]["status"]["message"]["parts"][0]["text"]


def test_explainer_subscribe_ends_with_artifact_then_final_status(monkeypatch):
    install_peer(monkeypatch, "math-calculator")
    client = TestClient(explainer_app)
    response = client.post("/", json=rpc("tasks/sendSubscribe", message("计算3+5")))
    kinds = []
    for event in parse_sse(response.text):
        result = event["result"]
        if "artifact" in result:
            kinds.append("artifact")
            assert result["artifact"]["parts"][0]["text"] == RESULT
        else:
            kinds.append(("status", result.get("final", False)))
    artifact_at = kinds.index("artifact")
    assert artifact_at > 0
    assert all(item[0] == "status" for item in kinds[:artifact_at])
    assert kinds[-1] == ("status", True)
