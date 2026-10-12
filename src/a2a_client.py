"""Send one calculation task to the explainer and poll tasks/get until it finishes."""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx


def artifact_text(task_body: dict) -> str:
    artifacts = task_body.get("artifacts") or []
    if not artifacts:
        return ""
    parts = artifacts[0].get("parts") or []
    return next((part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text"), "")


def task_payload(method: str, params: dict) -> dict:
    return {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}


async def main() -> None:
    agent_url = "http://127.0.0.1:8002"
    text = "计算3+5"
    delay = max(0, int(os.environ.get("DEMO_DELAY_MS", "0"))) / 1000
    async with httpx.AsyncClient(timeout=60) as client:
        card = (await client.get(f"{agent_url}/.well-known/agent.json")).json()
        print(f"发现Agent: {card['name']}")
        print(f"能力: {card['description']}")
        for skill in card["skills"]:
            print(f"技能: {skill['name']}")
        sent = (await client.post(agent_url, json=task_payload("tasks/send", {
            "id": str(uuid.uuid4()),
            "message": {"role": "user", "parts": [{"type": "text", "text": text}]},
        }))).json()
        if "error" in sent:
            raise SystemExit(sent["error"]["message"])
        task_id = sent["result"]["id"]
        state = sent["result"]["status"]["state"]
        print(f"发送: {text}\n状态: {state}")
        result = sent["result"]
        while state not in ("completed", "failed"):
            await asyncio.sleep(delay or 0.05)
            result = (await client.post(agent_url, json=task_payload("tasks/get", {"id": task_id}))).json()["result"]
            state = result["status"]["state"]
            message = ((result["status"].get("message") or {}).get("parts") or [{}])[0].get("text", "")
            print(f"状态: {state}" + (f" {message}" if message else ""))
        if state == "failed":
            raise SystemExit(artifact_text(result) or state)
        print(f"返回: {artifact_text(result)}")


if __name__ == "__main__":
    asyncio.run(main())
