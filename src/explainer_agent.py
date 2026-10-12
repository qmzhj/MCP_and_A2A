"""A2A explainer. It has no calculation skill, so it looks up the well-known Agent Card and delegates."""
from __future__ import annotations

import os
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI

from src.a2a import Task, TaskService, install_a2a
from src.trace import pause, record

app = FastAPI(title="Explainer A2A Agent")
REQUIRED_SKILL = "math-calculator"
CALCULATION_WORDS = ("计算", "加", "减", "乘", "除", "次方", "+", "*", "/", "^", "add", "multiply", "power")

AGENT_CARD = {
    "name": "ExplainerAgent",
    "description": "Receives a task, looks up skills at the well-known Agent Card, and returns the delegated result.",
    "url": "http://127.0.0.1:8002",
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": False},
    "skills": [{
        "id": "explain-task",
        "name": "Explain and delegate",
        "description": "Finds an agent with the required skill and returns that agent's result.",
        "examples": ["计算3+5"],
    }],
}


def peer_urls() -> list[str]:
    raw = os.environ.get("EXPLAINER_PEERS", "http://127.0.0.1:8001")
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60)


def needs_calculation(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in CALCULATION_WORDS)


def skill_ids(card: dict[str, Any]) -> list[str]:
    return [skill.get("id", "") for skill in card.get("skills") or [] if isinstance(skill, dict)]


def select_calculator(cards: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]] | None:
    for url, card in cards:
        if REQUIRED_SKILL in skill_ids(card):
            return url, card
    return None


def peer_id(url: str) -> str:
    port = urlparse(url).port
    if port == 8001:
        return "calculator-agent"
    if port == 8002:
        return "explainer"
    return urlparse(url).netloc or url


def artifact_text(task_body: dict[str, Any]) -> str:
    artifacts = task_body.get("artifacts") or []
    if not artifacts:
        return ""
    parts = artifacts[0].get("parts") or []
    return next((part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text"), "")


def plain_outcome(sentence: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?) ([+×^]) (\d+(?:\.\d+)?) = (\d+(?:\.\d+)?)", sentence)
    if match is None:
        return sentence
    left, symbol, right, value = match.groups()
    if symbol == "+":
        return f"{left} 加 {right} 等于 {value}"
    if symbol == "×":
        return f"{left} 乘以 {right} 等于 {value}"
    return f"{left} 的 {right} 次方等于 {value}"


def status_message(task_body: dict[str, Any]) -> str:
    message = (task_body.get("status") or {}).get("message") or {}
    parts = message.get("parts") or []
    return next((part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text"), "")


async def announce(task: Task, state: str, message: str | None = None, final: bool = False) -> None:
    await task.emit_status(state, message, final=final)
    await record("explainer", "client", state, {"summary": message or state, "taskId": task.id})


async def fetch_card(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(f"{url}/.well-known/agent.json")
    response.raise_for_status()
    return response.json()


async def send_task(client: httpx.AsyncClient, url: str, text: str) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tasks/send",
        "params": {"id": str(uuid.uuid4()), "message": {"role": "user", "parts": [{"type": "text", "text": text}]}},
    }
    response = await client.post(f"{url}/", json=payload)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "tasks/send failed"))
    return data["result"]


async def get_task(client: httpx.AsyncClient, url: str, task_id: str) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tasks/get", "params": {"id": task_id}}
    response = await client.post(f"{url}/", json=payload)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "tasks/get failed"))
    return data["result"]


async def run_explanation(task: Task, text: str) -> None:
    await announce(task, "submitted", f"解释 Agent 收到题目：{text}")
    if not needs_calculation(text):
        await task.fail("这道题用不到计算。")
        await record("explainer", "client", "failed", {"summary": "这道题用不到计算。"})
        return
    await announce(task, "working", "解释 Agent 发现需要进行计算")
    if REQUIRED_SKILL in skill_ids(AGENT_CARD):
        await task.fail("解释 Agent 不应该自己公布计算技能。")
        return
    await announce(task, "working", "解释 Agent 发现自己没有计算技能")
    await record("explainer", "plaza", "查看广场", {
        "path": "/.well-known/agent.json",
        "summary": "A2A 能力发现：向约定好的 well-known地址（“技能广场”）发送HTTP GET请求，获取agent技能卡片",
    })

    cards: list[tuple[str, dict[str, Any]]] = []
    client = client_factory()
    try:
        for url in peer_urls():
            await pause()
            card = await fetch_card(client, url)
            peer = peer_id(url)
            matched = REQUIRED_SKILL in skill_ids(card)
            if matched:
                await announce(task, "working", "发现计算 Agent 具有计算技能")
            else:
                await record("explainer", peer, "查看广场", {
                    "path": "/.well-known/agent.json",
                    "summary": "看过这张卡片，上面没有计算技能",
                })
            cards.append((url, card))
        chosen = select_calculator(cards)
        if chosen is None:
            await task.fail("“技能广场”上没有会计算的 Agent")
            await record("explainer", "client", "failed", {"summary": "“技能广场”上没有会计算的 Agent"})
            return
        url, _card = chosen
        peer = peer_id(url)
        await pause()
        await record("explainer", peer, "tasks/send", {"summary": "A2A 的任务委托：通过 tasks/send 把计算任务交给计算 Agent"})
        sent = await send_task(client, url, text)
        remote_id = sent["id"]
        result_text = ""
        told_still_working = False
        while True:
            await pause()
            got = await get_task(client, url, remote_id)
            remote_state = (got.get("status") or {}).get("state", "")
            result_text = artifact_text(got)
            if remote_state == "completed" and result_text:
                outcome = plain_outcome(result_text)
                value = outcome.rsplit("等于 ", 1)[-1] if "等于 " in outcome else outcome
                summary = f"计算agent回复A2A GET请求：计算完成，结果为{value}"
            elif remote_state == "working":
                if told_still_working:
                    continue
                summary = "回复A2A请求：正在计算"
                told_still_working = True
            elif remote_state == "failed":
                summary = "计算没有完成"
            else:
                summary = "回复A2A请求：正在计算"
            await record("explainer", peer, "tasks/get", {"summary": "A2A GET请求：询问计算进度"})
            await record(peer, "explainer", "tasks/get", {"summary": summary, "state": remote_state})
            if remote_state in ("completed", "failed"):
                break
    finally:
        await client.aclose()

    if remote_state == "failed":
        message = status_message(got) or "计算 Agent 任务失败。"
        await task.fail(message)
        await record("explainer", "client", "failed", {"summary": message})
        return
    await task.emit_artifact(result_text)
    await record(
        "explainer",
        "client",
        "TaskArtifactUpdateEvent",
        {"summary": f"计算 Agent 得到结果：{plain_outcome(result_text)}", "taskId": task.id},
    )
    await announce(task, "completed", "这轮任务结束", final=True)


service = TaskService("explainer", run_explanation)
install_a2a(app, AGENT_CARD, service)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "explainer-agent"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
