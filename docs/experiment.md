# 实验记录

## 1. 实验目标

观察这条链路：用户把「计算3+5」交给解释 Agent；解释 Agent 确认自己没有计算技能，到广场读取 `/.well-known/agent.json`；找到公布了 `math-calculator` 的计算 Agent 后，用 A2A `tasks/send` 委托，再用 `tasks/get` 取回结果；计算 Agent 调用 MCP `tools/call`；结果原文回到解释 Agent，再交给用户。

页面用 `tasks/sendSubscribe` 订阅解释 Agent，在同一条 SSE 上接收 `TaskStatusUpdateEvent` 和 `TaskArtifactUpdateEvent`。

## 2. 运行结果

| 步骤 | 协议 | 结果 |
| --- | --- | --- |
| 查看广场 | `GET /.well-known/agent.json` | 选中技能 `math-calculator` |
| 委托计算 | A2A `tasks/send` 然后 `tasks/get` | `计算结果: 3 + 5 = 8（MCP工具返回: 8）` |
| 执行计算 | MCP `tools/call add` | 8 |

演示脚本把 `DEMO_DELAY_MS` 设为 1500，方便在页面上看出 `working` 和后续的完成结果。自动化测试把延迟设为 0。

## 3. 协议观察

- 广场是 A2A 约定的技能公布位置：每个 Agent 自己的 `/.well-known/agent.json`。页面上的广场方框表示这个位置，不是另一台注册服务器。
- `tasks/send` 立刻返回 `working` 和任务编号。`tasks/get` 再用这个编号查询状态；完成后结果在 `artifacts` 里。
- `tasks/sendSubscribe` 用同一次 HTTP 响应作为 SSE。状态变化是 `TaskStatusUpdateEvent`，正文是 `TaskArtifactUpdateEvent`，结束时 `final` 为 `true`。
- MCP 的 `tools/list` 用 JSON Schema 描述工具参数。A2A 负责任务委托，MCP 负责工具执行。
- 服务只绑定 `127.0.0.1`。这次没有实现 `tasks/cancel`、`tasks/resubscribe`、推送通知、认证和 TLS。

## 4. 设计权衡

stdio 适合同机子进程通信。本实验使用 HTTP，是为了把解释 Agent、计算 Agent 和计算工具分成独立进程，并在页面上显示每一次调用。

## 5. 演示命令

```bash
export DEMO_DELAY_MS=1500
python -m pytest -q
./run_demo.sh
python src/a2a_client.py
```

通信日志写在标准输出和 `logs/trace.jsonl`。演示页订阅这些事件，把「查看广场」画在解释 Agent、计算 Agent 和广场之间的连线上。
