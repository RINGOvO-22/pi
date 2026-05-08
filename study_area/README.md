# Agent 应用开发学习计划总览

本目录用于记录基于 Pi 项目的 Agent 应用开发学习路线。

推荐学习主线：

```text
packages/ai → packages/agent → packages/coding-agent
```

这条路线对应一个 Agent 应用从底层到产品化的三层架构：

```text
┌─────────────────────────────────────┐
│ packages/coding-agent               │
│ 具体应用：CLI、工具、会话、配置、UI   │
└─────────────────────────────────────┘
                  ↓ uses
┌─────────────────────────────────────┐
│ packages/agent                      │
│ Agent runtime：loop、state、events   │
└─────────────────────────────────────┘
                  ↓ uses
┌─────────────────────────────────────┐
│ packages/ai                         │
│ LLM 抽象：provider、stream、tools     │
└─────────────────────────────────────┘
```

一句话概括：

- `packages/ai`：负责“怎么调用模型”
- `packages/agent`：负责“怎么让模型循环使用工具”
- `packages/coding-agent`：负责“怎么做成一个真实 coding agent 产品”

## 学习目标

通过阅读该项目，重点掌握 Agent 应用开发中的以下能力：

1. 模型抽象：统一 OpenAI / Anthropic / Gemini 等不同 provider。
2. 消息结构：理解 system / user / assistant / toolResult 的组织方式。
3. 工具调用：理解 schema、参数校验、执行、结果回填。
4. Agent Loop：理解模型调用和工具调用如何循环。
5. 应用工程化：理解会话、配置、权限、UI、错误恢复、上下文管理。

## 推荐阅读顺序

```text
第一阶段：LLM 调用基础
packages/ai/README.md
packages/ai/src/types.ts
packages/ai/src/stream.ts

第二阶段：Agent 核心循环
packages/agent/README.md
packages/agent/src/types.ts
packages/agent/src/agent-loop.ts
packages/agent/src/agent.ts

第三阶段：Coding Agent 产品化
packages/coding-agent/README.md
packages/coding-agent/src/core/agent-session.ts
packages/coding-agent/src/core/agent-session-runtime.ts
packages/coding-agent/src/core/system-prompt.ts
packages/coding-agent/src/utils/tools-manager.ts
```

## 本目录文件

- [01-ai.md](./01_ai//01-ai.md)：学习 `packages/ai`，理解 LLM 抽象层。
- [02-agent.md](./02_agent//02-agent.md)：学习 `packages/agent`，理解 Agent Runtime 和 Agent Loop。
- [03-coding-agent.md](./03_coding_agent//03-coding-agent.md)：学习 `packages/coding-agent`，理解产品化 Coding Agent。
- [04-practice.md](./04_practice//04-practice.md)：建议练习任务，用于巩固理解。
