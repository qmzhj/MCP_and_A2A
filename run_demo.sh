#!/usr/bin/env bash
# 启动计算工具、计算 Agent、解释 Agent 和演示页。Ctrl+C 会一起停下。
set -euo pipefail
cd "$(dirname "$0")"
export DEMO_DELAY_MS="${DEMO_DELAY_MS:-0}"

pick_python() {
  if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    echo "${CONDA_PREFIX}/bin/python"
    return
  fi
  if [[ -x .venv/bin/python ]]; then
    echo ".venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return
  fi
  echo python
}

PY="$(pick_python)"
if ! "$PY" -c "import fastapi, uvicorn, httpx" >/dev/null 2>&1; then
  echo "当前 Python 缺少依赖：$PY" >&2
  echo "请先激活 conda 环境，或执行: $PY -m pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p logs
pids=()
cleanup() {
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

start() {
  local name="$1"
  shift
  "$@" >"logs/${name}.log" 2>&1 &
  pids+=("$!")
}

wait_http() {
  local url="$1"
  local name="$2"
  local _try
  for _try in $(seq 1 50); do
    if "$PY" -c "import urllib.request; urllib.request.urlopen('${url}', timeout=0.5)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  echo "${name} 没有启动成功。最后几行日志：" >&2
  tail -n 20 "logs/${name}.log" >&2 || true
  exit 1
}

start calculator-tool "$PY" -m uvicorn src.calculator_tool_server:app --host 127.0.0.1 --port 8000
start calculator-agent "$PY" -m uvicorn src.calculator_agent:app --host 127.0.0.1 --port 8001
start explainer-agent "$PY" -m uvicorn src.explainer_agent:app --host 127.0.0.1 --port 8002
start demo-ui "$PY" -m uvicorn src.demo_ui:app --host 127.0.0.1 --port 8090

wait_http "http://127.0.0.1:8000/health" calculator-tool
wait_http "http://127.0.0.1:8001/health" calculator-agent
wait_http "http://127.0.0.1:8002/health" explainer-agent
wait_http "http://127.0.0.1:8090/health" demo-ui

echo "已启动（DEMO_DELAY_MS=${DEMO_DELAY_MS}，Python: ${PY}）"
echo "演示页面  http://127.0.0.1:8090"
echo "计算工具  http://127.0.0.1:8000/health"
echo "计算 Agent http://127.0.0.1:8001/.well-known/agent.json"
echo "解释 Agent http://127.0.0.1:8002/.well-known/agent.json"
echo "日志目录  logs/"
echo "按 Ctrl+C 停止全部服务"
wait
