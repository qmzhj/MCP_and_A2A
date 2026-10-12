# MCP + A2A 智能体互联网协议实验

解释 Agent 收到「计算3+5」后，发现自己没有计算技能，就到广场查看 Agent Card，把任务委托给计算 Agent。计算 Agent 再通过 MCP 调用计算工具，并把原文结果交回解释 Agent。

```text
agent_protocol_lab/
|-- src/
|   |-- calculator_tool_server.py   MCP 计算工具，端口 8000
|   |-- calculator_agent.py         A2A 计算 Agent，端口 8001
|   |-- explainer_agent.py          A2A 解释 Agent，端口 8002
|   |-- a2a.py                      共用的 tasks/send、tasks/sendSubscribe、tasks/get
|   |-- a2a_client.py               命令行：tasks/send 后循环 tasks/get
|   |-- demo_ui.py                  演示页，端口 8090
|   `-- static/index.html           四个方框：解释 Agent、广场、计算 Agent、计算工具
|-- tests/
|-- docs/
|-- run_demo.sh
|-- run_calculator_tool.ps1
|-- run_calculator_agent.ps1
`-- run_explainer_agent.ps1
```

广场不是单独的服务器。每个 Agent 在自己的 `/.well-known/agent.json` 公布技能。

## 运行环境

需要 Python 3.11+。可以用标准虚拟环境，也可以用 conda。

```bash
cd agent_protocol_lab
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

conda：

```bash
conda create -n agent-protocol python=3.11 -y
conda activate agent-protocol
pip install -r requirements.txt
```

## 启动演示

先激活要用的 Python 环境（conda 或 `.venv`），再执行启动脚本。脚本会拉起 8000、8001、8002 和 8090。各服务的输出写在 `logs/`。页面上每点一次「下一步」，才展示下一条通信。

```bash
conda activate agent-protocol
chmod +x run_demo.sh
./run_demo.sh
```

浏览器打开 `http://127.0.0.1:8090`。输入框里已填「计算3+5」，提交后页面用 `tasks/sendSubscribe` 订阅解释 Agent。按 Ctrl+C 会停下全部服务。

也可以分四个终端启动，并先设置延迟：

```bash
export DEMO_DELAY_MS=1500
python -m uvicorn src.calculator_tool_server:app --host 127.0.0.1 --port 8000
python -m uvicorn src.calculator_agent:app --host 127.0.0.1 --port 8001
python -m uvicorn src.explainer_agent:app --host 127.0.0.1 --port 8002
python -m uvicorn src.demo_ui:app --host 127.0.0.1 --port 8090
```

Windows 可分别运行 `run_calculator_tool.ps1`、`run_calculator_agent.ps1`、`run_explainer_agent.ps1`，再启动 `demo_ui`。

命令行客户端对解释 Agent 发 `tasks/send`，再循环 `tasks/get`：

```bash
python src/a2a_client.py
```

## 自动化验证

```bash
python -m pytest -q
```

测试把 `DEMO_DELAY_MS` 设为 0，不要求中间查询必须先看到 `working`。

## 协议边界

MCP 使用 JSON-RPC 2.0 over HTTP。A2A 使用 Agent Card、`tasks/send`、`tasks/sendSubscribe` 和 `tasks/get`。未实现取消任务、重新订阅、推送通知、认证和 TLS。这些边界见 `docs/experiment.md`。



