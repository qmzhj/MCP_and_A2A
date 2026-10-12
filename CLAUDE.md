# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 MCP + A2A 协议的教学演示实验，展示「广场公布技能 → 解释 Agent 发现计算 Agent → 任务委托 → 工具执行」的链路。所有代码都位于本目录（注意：本仓库在磁盘上有一个同名嵌套目录，实际的 `src/`、`tests/`、`docs/` 都在此层级）。

## 常用命令

```bash
# 环境准备（Linux/macOS）
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 运行测试（不需要启动任何服务，TestClient 直接驱动 FastAPI app）
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_protocol.py::test_mcp_lists_and_calls_tools -q

# 启动演示（DEMO_DELAY_MS 默认 1500）
./run_demo.sh

# 或分四个终端
export DEMO_DELAY_MS=1500
.venv/bin/python -m uvicorn src.calculator_tool_server:app --host 127.0.0.1 --port 8000
.venv/bin/python -m uvicorn src.calculator_agent:app --host 127.0.0.1 --port 8001
.venv/bin/python -m uvicorn src.explainer_agent:app --host 127.0.0.1 --port 8002
.venv/bin/python -m uvicorn src.demo_ui:app --host 127.0.0.1 --port 8090

# 命令行客户端（需三个协议服务已运行；对 8002 发 tasks/send，再循环 tasks/get）
.venv/bin/python src/a2a_client.py
```

演示页是 `http://127.0.0.1:8090`。Windows 可使用 `run_calculator_tool.ps1`、`run_calculator_agent.ps1`、`run_explainer_agent.ps1`。

## 架构

三个协议进程加一个旁路演示页，通过 JSON-RPC 2.0 over HTTP 通信：

- **`src/calculator_tool_server.py`（端口 8000）** — MCP 计算工具。暴露 `add` / `multiply` / `power`，在 `/mcp` 处理 `initialize`、`tools/list`、`tools/call`。
- **`src/calculator_agent.py`（端口 8001）** — A2A 计算 Agent。在 `/.well-known/agent.json` 公布技能 `math-calculator`。支持 `tasks/send`、`tasks/sendSubscribe`、`tasks/get`。收到计算任务后调用 8000 的 MCP `tools/call`。
- **`src/explainer_agent.py`（端口 8002）** — A2A 解释 Agent。技能只有 `explain-task`。收到「计算3+5」后读取对等地址的 Agent Card，选中 `math-calculator`，对其 `tasks/send`，再循环 `tasks/get`，把计算原文交给调用方。对等地址默认 `http://127.0.0.1:8001`，可用 `EXPLAINER_PEERS` 覆盖。
- **`src/a2a.py`** — 两个 Agent 共用的任务表、状态机和 SSE。`tasks/send` 与 `tasks/sendSubscribe` 执行同一段后台任务。
- **`src/demo_ui.py`（端口 8090）** — 演示页。四个方框是解释 Agent、广场、计算 Agent、计算工具。广场表示约定路径 `/.well-known/agent.json`，不是独立进程。
- **`src/a2a_client.py`** — 命令行对解释 Agent 发 `tasks/send` 并轮询 `tasks/get`。
- **`src/trace.py`** — 标准输出、`logs/trace.jsonl`，以及投递到演示页 `/events`。`DEMO_DELAY_MS` 控制状态变化和跨服务请求前的等待；测试里为 0。

### 关键实现细节

- 解释 Agent 到计算 Agent 的发现请求打到计算 Agent 自己的 `/.well-known/agent.json`。日志的 `target` 是被查看的 Agent，动作为「查看广场」。
- 计算 Agent 的口令解析沿用原来的规则：抽取数字后按加、乘、次方的顺序判断。`计算3+5` 含 `+`，走 `add`。
- 两个服务都只绑定 `127.0.0.1`，且无认证/TLS。未实现 `tasks/cancel`、`tasks/resubscribe` 和推送通知。

### 测试策略

`tests/test_protocol.py` 使用 FastAPI `TestClient`。计算工具和两个 Agent 的协议方法不需要真实端口。解释 Agent 的跨服务委托用 `httpx.MockTransport` 验证「查看广场、send、get、原文交回」。`tests/conftest.py` 关闭远程日志和演示延迟。

## 参考文档

- `docs/experiment.md` — 实验目标、协议观察与 HTTP 进程边界
- `README.md` — 启动和验证命令
