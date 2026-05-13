# 02 Agent Outline

目标: 在 P8 mini_pi_ai 的基础上, 对照 `packages/agent` 源码理解 agent loop 的工程化实现。

核心问题:

```text
packages/ai 负责模型调用与统一消息/事件
packages/agent 负责如何把模型、工具、状态、循环控制组织成 agent 行为
```

## 学习顺序

### 1. Agent 层在做什么

源码入口:

```text
packages/agent/src/types.ts
packages/agent/src/agent-loop.ts
```

重点问题:

```text
Agent 和单次 LLM call 有什么区别
agent loop 的输入/输出是什么
loop state 如何表示
什么时候继续循环
什么时候停止
```

对应 P8:

```text
p8_mini_pi_ai/agent_loop.py
```

---

### 2. Agent 类型系统

阅读:

```text
packages/agent/src/types.ts
```

重点关注:

```text
Agent 输入类型
Agent 输出类型
Agent 事件类型
工具执行相关类型
中止/错误相关类型
```

目标:

```text
把 packages/agent 的类型映射到 P8 的 Context / AssistantMessage / ToolCall / ToolResultMessage。
```

---

### 3. Agent loop 主流程

阅读:

```text
packages/agent/src/agent-loop.ts
```

重点关注:

```text
while / loop 结构
模型调用位置
stream event 消费位置
tool call 提取位置
tool 执行位置
tool result 回填位置
stop condition
```

对应 P8:

```text
run_agent_loop()
consume_events()
get_tool_calls()
execute_tool_call()
```

---

### 4. 工具执行与错误处理

重点问题:

```text
工具不存在怎么办
工具参数错误怎么办
工具执行异常怎么办
工具结果如何进入下一轮模型调用
```

对应 P8:

```text
tools.py
execute_tool_call()
```

可做练习:

```text
给 P8 增加一个会失败的工具
观察 ToolResultMessage(is_error=True) 如何影响下一轮回答
```

---

### 5. Agent 事件与可观察性

重点问题:

```text
agent loop 是否也产生事件
模型 stream event 和 agent event 有什么区别
UI / 日志 / hook 如何消费这些事件
```

对应 P8:

```text
stream.py
agent_loop.py consume_events()
```

理解目标:

```text
stream events 是模型生成过程
agent events 是 agent 行为过程
```

---

### 6. Abort / stop / limits

重点问题:

```text
如何取消运行
如何限制最大轮数
如何处理 context overflow
如何防止无限工具循环
```

对应 P8:

```text
run_agent_loop(max_turns=5)
```

可做练习:

```text
让模型持续请求工具, 观察 max_turns 如何保护循环
```

---

### 7. P9 练习: minimal agent package

建议创建:

```text
study_area/02_agent/p9_minimal_agent_loop.py
```

目标:

```text
不再重新写 Qwen adapter
复用 P8 的 qwen/context/tools/memory
只重写一个更接近 packages/agent 的 agent loop 结构
```

练习重点:

```text
把 run_agent_loop 拆成更清晰的阶段
增加 AgentEvent
增加 loop state
增加 stop reason
```

---

## 对照关系

```text
P8 mini_pi_ai                     packages/agent
------------------------------------------------------------
Context                           agent state / input context
stream_qwen()                     model stream call
AssistantMessageEvent             model stream event
run_agent_loop()                  agent loop
ToolCall                          tool request
execute_tool_call()               tool executor
ToolResultMessage                 tool observation/result
max_turns                         loop limit / safety guard
context_memory.json               persisted session state
```

## 阶段目标

完成 02_agent 后, 应该能回答:

```text
1. agent loop 比 LLM call 多了什么
2. tool call 在 agent loop 中是什么角色
3. agent 如何决定继续或停止
4. stream event 和 agent event 的区别是什么
5. 为什么真实 agent 需要 max turns / abort / error handling
```
