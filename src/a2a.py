"""Shared A2A task store, JSON-RPC methods, and SSE subscription."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.trace import pause, record

Runner = Callable[["Task", str], Awaitable[None]]


class Task:
    def __init__(self, task_id: str) -> None:
        self.id = task_id
        self.state = "working"
        self.message: str | None = None
        self.artifacts: list[dict[str, Any]] = []
        self.final = False
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def public(self) -> dict[str, Any]:
        status: dict[str, Any] = {"state": self.state}
        if self.message:
            status["message"] = {"role": "agent", "parts": [{"type": "text", "text": self.message}]}
        body: dict[str, Any] = {"id": self.id, "status": status}
        if self.state == "completed" and self.artifacts:
            body["artifacts"] = self.artifacts
        return body

    async def emit_status(self, state: str, message: str | None = None, final: bool = False) -> None:
        await pause()
        self.state = state
        self.message = message
        self.final = final
        status: dict[str, Any] = {"state": state}
        if message:
            status["message"] = {"role": "agent", "parts": [{"type": "text", "text": message}]}
        await self.queue.put({"id": self.id, "status": status, "final": final})
        if final:
            await self.queue.put(None)

    async def emit_artifact(self, text: str) -> None:
        await pause()
        artifact = {"parts": [{"type": "text", "text": text}], "index": 0}
        self.artifacts = [artifact]
        await self.queue.put({"id": self.id, "artifact": artifact})

    async def fail(self, message: str) -> None:
        if self.final:
            return
        await self.emit_status("failed", message, final=True)


class TaskService:
    def __init__(self, agent_id: str, runner: Runner) -> None:
        self.agent_id = agent_id
        self.runner = runner
        self.tasks: dict[str, Task] = {}
        self.jobs: set[asyncio.Task[None]] = set()

    def create(self, requested_id: Any) -> Task:
        task_id = requested_id if isinstance(requested_id, str) and requested_id else str(uuid.uuid4())
        if task_id in self.tasks:
            task_id = str(uuid.uuid4())
        task = Task(task_id)
        self.tasks[task_id] = task
        return task

    async def execute(self, task: Task, text: str) -> None:
        try:
            await self.runner(task, text)
            if not task.final:
                await task.fail("任务结束时没有最终状态。")
        except Exception as exc:
            await task.fail(str(exc))

    def schedule(self, task: Task, text: str) -> None:
        job = asyncio.create_task(self.execute(task, text))
        self.jobs.add(job)
        job.add_done_callback(self.jobs.discard)

    async def stream(self, request_id: Any, task: Task, text: str):
        self.schedule(task, text)
        while True:
            event = await task.queue.get()
            if event is None:
                break
            payload = {"jsonrpc": "2.0", "id": request_id, "result": event}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def message_text(params: dict[str, Any]) -> str:
    parts = ((params.get("message") or {}).get("parts") or [])
    return next((part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text"), "")


def rpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def install_a2a(app: FastAPI, card: dict[str, Any], service: TaskService) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/.well-known/agent.json")
    async def agent_card() -> dict[str, Any]:
        return card

    @app.post("/")
    async def handle_task(request: Request, background: BackgroundTasks):
        try:
            body = await request.json()
        except Exception:
            return rpc_error(None, -32700, "Parse error")
        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        if body.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return rpc_error(request_id, -32600, "Invalid Request")
        if not isinstance(params, dict):
            return rpc_error(request_id, -32602, "Invalid params")

        if method in ("tasks/send", "tasks/sendSubscribe"):
            text = message_text(params)
            task = service.create(params.get("id"))
            if service.agent_id == "explainer":
                summary = f"用户把题目「{text}」交给解释 Agent" if text else "用户发来一个任务"
            elif service.agent_id == "calculator-agent":
                summary = f"收到任务「{text}」" if text else "收到一道计算题"
            else:
                summary = f"收到题目「{text}」" if text else method
            await record("client", service.agent_id, method, {"summary": summary, "taskId": task.id})
            if method == "tasks/send":
                background.add_task(service.execute, task, text)
                if service.agent_id == "calculator-agent" and task.state == "working":
                    await record(
                        "calculator-agent",
                        "explainer",
                        "tasks/send",
                        {"summary": "计算agent回复解释agent的tasks/send：计算 Agent 已接到任务，正在计算", "taskId": task.id},
                    )
                return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": task.public()})
            return StreamingResponse(
                service.stream(request_id, task, text),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        if method == "tasks/get":
            task_id = params.get("id")
            task = service.tasks.get(task_id) if isinstance(task_id, str) else None
            if task is None:
                await record("client", service.agent_id, "tasks/get", {"summary": "没有找到这张任务"})
                return rpc_error(request_id, -32001, "Task not found")
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": task.public()})

        return rpc_error(request_id, -32601, f"Method not found: {method}")
