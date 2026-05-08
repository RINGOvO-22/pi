# 第二阶段：`packages/agent` —— Agent Runtime 层

## 这一层解决什么问题？

`packages/agent` 解决的是：

```text
如何让 LLM 变成一个会循环、会用工具、会维护状态的 Agent？
```

这是学习 Agent 应用开发最核心的一层。

## 可以如何理解？

这一层是 Agent Engine / Agent Runtime。

它把一次模型调用扩展成完整的 Agent 行为：

```text
user prompt
  ↓
LLM response
  ↓
tool calls?
  ↓
execute tools
  ↓
tool results
  ↓
next LLM response
  ↓
final answer
```

## 学习重点

重点理解以下能力：

- Agent 如何维护 messages。
- 用户输入如何进入 context。
- LLM 响应如何流式进入 Agent。
- assistant message 中的 tool call 如何被识别。
- 工具如何被查找、校验、执行。
- tool result 如何回填给模型。
- Agent Loop 何时继续、何时结束。
- Agent 事件如何通知 UI 或上层应用。

## 推荐阅读文件

```text
packages/agent/README.md
packages/agent/src/types.ts
packages/agent/src/agent-loop.ts
packages/agent/src/agent.ts
```

其中最重要的是：

```text
packages/agent/src/agent-loop.ts
```

## `agent-loop.ts` 阅读主线

建议抓三条线：

### 1. 控制流

```text
agentLoop → runAgentLoop → runLoop
```

重点看 Agent 是如何一轮一轮运行的。

### 2. LLM 流

```text
streamAssistantResponse
```

重点理解：

```text
AgentMessage[]
  ↓ transformContext
AgentMessage[]
  ↓ convertToLlm
Message[]
  ↓ streamSimple
AssistantMessage
```

### 3. 工具流

```text
executeToolCalls
prepareToolCall
executePreparedToolCall
finalizeExecutedToolCall
createToolResultMessage
```

重点理解：

```text
toolCall
  ↓
validate args
  ↓
beforeToolCall
  ↓
execute
  ↓
afterToolCall
  ↓
toolResult
```

## 阅读时带着这些问题

1. `agentLoop` 和 `agentLoopContinue` 有什么区别？
2. 为什么要区分 `AgentMessage` 和 LLM `Message`？
3. `transformContext` 和 `convertToLlm` 分别解决什么问题？
4. 工具调用为什么要有 prepare / execute / finalize 三个阶段？
5. 工具执行失败时，为什么不直接让整个 loop 崩掉？
6. sequential 和 parallel 两种工具执行模式有什么区别？
7. `shouldStopAfterTurn` 适合用来做什么？

## 学完后应该能回答

- Agent Loop 的核心状态机是怎样的？
- 一次用户输入如何触发多轮模型调用？
- 工具结果如何被放回上下文？
- 事件流如何支撑 UI 更新？

## 这一层和上下层的关系

```text
packages/agent 使用 packages/ai 调用模型
packages/coding-agent 使用 packages/agent 构建真实 CLI 产品
```

一句话：

```text
packages/agent 是从 LLM SDK 到 Agent App 的中间核心层。
```
