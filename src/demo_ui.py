"""Demo page and live trace stream. This process is an observer, not an agent."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

app = FastAPI(title="Protocol Demo")
PAGE = Path(__file__).resolve().parent / "static" / "index.html"
events: list[dict] = []
subscribers: list[asyncio.Queue] = []


def encode(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "demo-ui"}


@app.post("/events")
async def ingest(request: Request) -> dict[str, bool]:
    event = await request.json()
    events.append(event)
    for queue in subscribers:
        queue.put_nowait(event)
    return {"ok": True}


@app.get("/stream")
async def stream() -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()
    subscribers.append(queue)

    async def generate():
        try:
            for event in list(events):
                yield encode(event)
            while True:
                yield encode(await queue.get())
        finally:
            subscribers.remove(queue)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(PAGE)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)
