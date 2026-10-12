"""Minimal MCP-style calculator server over Streamable HTTP."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.trace import record

app = FastAPI(title="Calculator MCP Server")

TOOLS = [
    {
        "name": "add",
        "description": "Add two numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "multiply",
        "description": "Multiply two numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "power",
        "description": "Raise a number to a power.",
        "inputSchema": {
            "type": "object",
            "properties": {"base": {"type": "number"}, "exponent": {"type": "number"}},
            "required": ["base", "exponent"],
        },
    },
]


def rpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def number(arguments: dict[str, Any], name: str) -> float:
    value = arguments.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"argument '{name}' must be a number")
    return float(value)


def call_tool(name: str, arguments: dict[str, Any]) -> float:
    if name == "add":
        return number(arguments, "a") + number(arguments, "b")
    if name == "multiply":
        return number(arguments, "a") * number(arguments, "b")
    if name == "power":
        return number(arguments, "base") ** number(arguments, "exponent")
    raise KeyError(name)


def shown_number(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return f"{float(value):g}"


def tool_request(name: str, arguments: dict[str, Any]) -> str:
    if name == "power":
        return f"计算工具收到：求 {shown_number(arguments.get('base'))} 的 {shown_number(arguments.get('exponent'))} 次方"
    if name == "multiply":
        return f"计算工具收到：把 {shown_number(arguments.get('a'))} 乘以 {shown_number(arguments.get('b'))}"
    if name == "add":
        return f"计算工具收到：把 {shown_number(arguments.get('a'))} 和 {shown_number(arguments.get('b'))} 相加"
    return f"计算工具收到一个无法识别的请求：{name}"


def tool_reply(name: str, arguments: dict[str, Any], result: float) -> str:
    value = f"{result:g}"
    if name == "power":
        return f"计算工具答：{shown_number(arguments.get('base'))} 的 {shown_number(arguments.get('exponent'))} 次方等于 {value}"
    if name == "multiply":
        return f"计算工具答：{shown_number(arguments.get('a'))} 乘以 {shown_number(arguments.get('b'))} 等于 {value}"
    return f"计算工具答：{shown_number(arguments.get('a'))} 加 {shown_number(arguments.get('b'))} 等于 {value}"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "calculator-tool"}


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return rpc_error(None, -32700, "Parse error")

    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    if body.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return rpc_error(request_id, -32600, "Invalid Request")
    if method == "initialize":
        await record("client", "calculator-tool", "initialize", {"summary": "计算工具准备好了"})
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "calculator-mcp", "version": "1.0.0"},
            },
        })
    if method == "notifications/initialized":
        return JSONResponse(status_code=202, content={})
    if method == "tools/list":
        await record("client", "calculator-tool", "tools/list", {"summary": "查看计算工具有哪些功能"})
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return rpc_error(request_id, -32602, "Invalid tool arguments")
        await record("calculator-tool", "client", "tools/call", {"summary": tool_request(name, arguments)})
        try:
            result = call_tool(name, arguments)
        except KeyError:
            await record("calculator-tool", "calculator-agent", "tools/call", {"summary": f"计算工具没有这项功能：{name}"})
            return rpc_error(request_id, -32602, f"Unknown tool: {name}")
        except ValueError as exc:
            await record("calculator-tool", "calculator-agent", "tools/call", {"summary": f"计算工具没能完成：{exc}"})
            return rpc_error(request_id, -32602, str(exc))
        await record("calculator-tool", "calculator-agent", "tools/call", {"summary": tool_reply(name, arguments, result)})
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": str(result)}], "structuredContent": {"value": result}},
        })
    return rpc_error(request_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
