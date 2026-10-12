# 把演示提示改成白话

演示页上的橙色气泡、「下一步」下面的「下一条：…」、以及通信记录，显示的都是同一次通信的 `summary`。观众先看到的是这句短话，不是协议字段名。改展示文案时，只改这句人话；日志里的 `source`、`target`、`action` 继续留着，方便对照协议。

## 改哪一句

每个提示来自 `record(..., {"summary": "..."})` 或 `announce(...)` 的那句中文。页面用 `detail.summary` 做气泡文字。

| 出现位置 | 代码 |
| --- | --- |
| 解释 Agent 的进度 | `src/explainer_agent.py` 里 `announce` 的第三参，以及同文件里的 `summary=` |
| 计算 Agent 的进度 | `src/calculator_agent.py` 里的 `announce` 和 `call_summary` |
| 计算工具的调用 | `src/calculator_tool_server.py` 里的 `tool_call_summary` |
| 收到任务、查询任务 | `src/a2a.py` 里 `tasks/send`、`tasks/get` 的 `summary` |

气泡最宽大约 240 像素，一句话控制在 20 个字左右。讲协议名称时放在后半句，例如「把『计算3+5』交给计算 Agent（tasks/send）」。

## 写法

1. 先写谁在做什么，再写结果。不要只写方法名。
2. 角色用中文：解释 Agent、计算 Agent、计算工具、广场。不要在气泡里写 `explainer`、`calculator-agent`、`client`。
3. 广场说成「看对方公布的技能」，需要点明路径时再补 `/.well-known/agent.json`。
4. 状态词换成过程：`working` 不要单独出现；`completed` 写成「计算完成」；`TaskArtifactUpdateEvent` 写成「把结果交回来」。
5. 同一跳如果请求和响应各有一条提示，请求说「正在问」，响应说「得到了什么」。不要两条都只写 `tasks/get`。
6. 数字和算式留在句子里，例如「3 加 5 等于 8」。

## 现有提示怎么改

下面左列是现在会弹出来的字，右列是可以换成的说法。花括号里的内容保持动态生成。

| 现在的提示 | 建议改成 |
| --- | --- |
| 已收到「计算3+5」 | 解释 Agent 收到题目：计算3+5 |
| 需要计算能力但自己没有 | 这道题要会计算，解释 Agent 自己不会 |
| 正在广场查看技能 | 去广场看谁公布了计算技能 |
| GET /.well-known/agent.json math-calculator | 在广场上看到计算 Agent 会做计算 |
| GET /.well-known/agent.json | 看过这张卡片，上面没有计算技能 |
| 已找到计算 Agent | 找到了会计算的 Agent |
| tasks/send 计算3+5 | 把题目「计算3+5」交给计算 Agent |
| tasks/send working | 计算 Agent 已接单，正在算 |
| 正在查询计算结果 | 向计算 Agent 询问算完了没有 |
| tasks/get | 询问计算进度 |
| tasks/get working | 计算 Agent 还在算 |
| tasks/get completed 计算结果: 3 + 5 = 8（MCP工具返回: 8） | 算完了：3 加 5 等于 8 |
| 已接收计算任务 | 计算 Agent 收下了这道题 |
| 正在调用计算工具 add | 请计算工具做加法 |
| tools/call add(3, 5) | 计算工具收到：把 3 和 5 相加 |
| tools/call add(3, 5) -> 8 | 计算工具答：3 加 5 等于 8 |
| 计算结果: 3 + 5 = 8（MCP工具返回: 8） | 计算 Agent 得到结果：3 加 5 等于 8 |
| completed | 这轮任务结束 |
| 广场上找不到计算 Agent | 广场上没有会计算的 Agent |
| 这个任务不需要计算技能。 | 这道题用不到计算 |

乘法、乘方沿用同一句式：「请计算工具做乘法」「把 12 乘以 7」「2 的 10 次方等于 1024」。

## 不要改的部分

- JSON-RPC 方法名、Agent Card 路径、技能编号 `math-calculator` 仍放在代码和 `logs/trace.jsonl` 里。
- 通信记录如果还要给懂协议的人看，可以保留 `source → target`，只把后面的 `summary` 换成上表右列。
- 测试断言了结果原文 `计算结果: 3 + 5 = 8（MCP工具返回: 8）`。气泡可以改成人话，返回给用户的那句结果若要改，需要同时改 `src/calculator_agent.py` 的 `result_sentence` 和 `tests/test_protocol.py`。

## 改完怎么核对

重新打开演示页，发送「计算3+5」，连续点「下一步」。每一条气泡都应该能不看代码就回答两个问题：谁在说话，这一步做成了什么。
