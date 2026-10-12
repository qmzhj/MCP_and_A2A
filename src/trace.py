"""Record cross-process protocol hops and optionally slow them down for the demo."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def delay_ms() -> int:
    raw = os.environ.get("DEMO_DELAY_MS", "0")
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def trace_log_path() -> Path:
    return Path(os.environ.get("TRACE_LOG", "logs/trace.jsonl"))


def trace_url() -> str:
    return os.environ.get("TRACE_URL", "http://127.0.0.1:8090/events")


async def pause() -> None:
    milliseconds = delay_ms()
    if milliseconds:
        await asyncio.sleep(milliseconds / 1000)


async def record(source: str, target: str, action: str, detail: dict[str, Any] | None = None) -> None:
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "target": target,
        "action": action,
        "detail": detail or {},
    }
    summary = event["detail"].get("summary") or action
    print(f"[trace] {event['ts']} {source} -> {target} {summary}", flush=True)
    path = trace_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    if os.environ.get("TRACE_REMOTE", "1") == "0":
        return
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            await client.post(trace_url(), json=event)
    except httpx.HTTPError:
        return
