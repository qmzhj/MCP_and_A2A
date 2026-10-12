"""A2A calculator agent. It publishes math-calculator and calls the MCP calculator tool."""
from __future__ import annotations

import os
import re
import uuid
from typing import Any

import httpx
from fastapi import FastAPI

from src.a2a import Task, TaskService, install_a2a
from src.trace import pause, record

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
app = FastAPI(title="Calculator A2A Agent")

AGENT_CARD = {
    "name": "MathAssistantAgent",
    "description": "A math assistant that delegates calculations to an MCP calculator.",
    "url": "http://127.0.0.1:8001",
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": False},
    "skills": [{
        "id": "math-calculator",
        "name": "Math calculation",
        "description": "Addition, multiplication, and exponentiation.",
        "examples": ["计算3加5", "计算12乘7", "计算2的10次方"],
    }],
}


def extract_numbers(text: str) -> list[float]:
    return [float(value) for value in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]


def choose_operation(text: str, numbers: list[float]) -> tuple[str, str, dict[str, float]] | None:
    if len(numbers) < 2:
        return None
    lowered = text.lower()
    if any(word in lowered for word in ("加", "add", "+")):
        return "add", "+", {"a": numbers[0], "b": numbers[1]}
    if any(word in lowered for word in ("乘", "multiply", "*")):
        return "multiply", "×", {"a": numbers[0], "b": numbers[1]}
    if any(word in lowered for word in ("次方", "power", "^")):
        return "power", "^", {"base": numbers[0], "exponent": numbers[1]}
    return None


def result_sentence(left: float, symbol: str, right: float, result: float) -> str:
    return f"计算结果: {left:g} {symbol} {right:g} = {result:g}（MCP工具返回: {result:g}）"


def spoken_math(left: float, symbol: str, right: float, result: float | None = None) -> str:
    a, b = f"{left:g}", f"{right:g}"
    if symbol == "+":
        phrase = f"{a} 加 {b}"
    elif symbol == "×":
        phrase = f"{a} 乘以 {b}"
    else:
        phrase = f"{a} 的 {b} 次方"
    if result is None:
        return phrase
    return f"{phrase} 等于 {result:g}"


async def call_mcp_tool(name: str, arguments: dict[str, float]) -> float:
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(MCP_URL, json=payload)
        response.raise_for_status()
        data = response.json()
    if "error" in data:
        raise ValueError(data["error"]["message"])
    return float(data["result"]["structuredContent"]["value"])


async def announce(task: Task, state: str, message: str | None = None, final: bool = False, note: str | None = None) -> None:
    await task.emit_status(state, message, final=final)
    detail = {"summary": message or state, "taskId": task.id}
    if note:
        detail["note"] = note
    await record("calculator-agent", "client", state, detail)


async def run_calculation(task: Task, text: str) -> None:
    await announce(task, "submitted", "计算智能体开始进行计算")
    numbers = extract_numbers(text)
    if len(numbers) < 2:
        await task.emit_artifact("请提供两个数字，例如：计算3加5。支持加法、乘法和幂运算。")
        await announce(task, "completed", "这轮任务结束", final=True)
        return
    chosen = choose_operation(text, numbers)
    if chosen is None:
        await task.emit_artifact("暂不支持该运算。请使用加法、乘法或幂运算。")
        await announce(task, "completed", "这轮任务结束", final=True)
        return
    operation, symbol, arguments = chosen
    work = {
        "add": "计算智能体发现需要进行加法，准备调用计算工具",
        "multiply": "请计算工具做乘法",
        "power": "请计算工具做乘方",
    }
    await announce(
        task,
        "working",
        work[operation],
        note="在 MCP 中，连接建立后会进入初始化阶段，计算智能体会调用 tools/list 取回工具清单，从而知道自己有哪些工具可以调用。" if operation == "add" else None,
    )
    await pause()
    await record("calculator-agent", "calculator-tool", "tools/call", {"summary": f"向计算工具发送MCP请求：{text}"})
    result = await call_mcp_tool(operation, arguments)
    left = arguments.get("a", arguments.get("base", numbers[0]))
    right = arguments.get("b", arguments.get("exponent", numbers[1]))
    sentence = result_sentence(left, symbol, right, result)
    await task.emit_artifact(sentence)
    await record(
        "calculator-agent",
        "client",
        "TaskArtifactUpdateEvent",
        {"summary": f"计算智能体得到结果：{spoken_math(left, symbol, right, result)}，并更新task对象", "taskId": task.id},
    )
    await announce(task, "completed", "这轮任务结束", final=True)


service = TaskService("calculator-agent", run_calculation)
install_a2a(app, AGENT_CARD, service)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "calculator-agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
