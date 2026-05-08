# 第三阶段：`packages/coding-agent` —— 产品应用层

## 这一层解决什么问题？

`packages/coding-agent` 解决的是：

```text
如何把 Agent Runtime 做成一个真正可用的 Coding Agent 产品？
```

这是 Pi 的实际应用层，也就是用户真正使用的 CLI coding agent。

## 可以如何理解？

如果说：

```text
packages/ai 是模型接口
packages/agent 是 Agent 引擎
```

那么：

```text
packages/coding-agent 就是完整产品
```

它把 Agent Runtime 包装成一个可交互、可配置、可扩展、可恢复的开发工具。

## 学习重点

重点理解以下产品化能力：

- CLI 如何启动。
- 模型如何选择和配置。
- system prompt 如何构造。
- read / write / edit / bash 工具如何接入。
- session 如何保存和恢复。
- AGENTS.md 如何加载为项目上下文。
- slash commands 如何工作。
- 配置、权限、认证、错误恢复如何组织。
- 交互式 UI 如何和 Agent 事件流连接。
- skills / extensions / prompt templates 如何扩展产品能力。

## 推荐阅读文件

```text
packages/coding-agent/README.md
packages/coding-agent/src/main.ts
packages/coding-agent/src/cli.ts
packages/coding-agent/src/core/agent-session.ts
packages/coding-agent/src/core/agent-session-runtime.ts
packages/coding-agent/src/core/system-prompt.ts
packages/coding-agent/src/core/session-manager.ts
packages/coding-agent/src/core/slash-commands.ts
packages/coding-agent/src/utils/tools-manager.ts
```

建议先从这些文件开始：

```text
packages/coding-agent/README.md
packages/coding-agent/src/core/agent-session.ts
packages/coding-agent/src/core/agent-session-runtime.ts
packages/coding-agent/src/core/system-prompt.ts
packages/coding-agent/src/utils/tools-manager.ts
```

## 阅读时带着这些问题

1. 一个真实 Coding Agent 启动时需要初始化哪些东西？
2. system prompt 是如何拼装出来的？
3. 默认工具 read / write / edit / bash 是在哪里注册的？
4. session 中保存了哪些状态？
5. CLI / TUI 如何消费 `packages/agent` 发出的事件？
6. 用户配置如何影响 Agent 行为？
7. extension / skill / prompt template 分别解决什么扩展问题？

## 学完后应该能回答

- 如何基于 Agent Runtime 做一个具体应用？
- Coding Agent 和普通 Chat Agent 的差异在哪里？
- 一个可用 Agent 产品需要哪些工程能力？
- 如何扩展工具、prompt、配置和 UI？

## 这一层和前两层的关系

```text
packages/coding-agent
  ↓ uses
packages/agent
  ↓ uses
packages/ai
```

一句话：

```text
packages/coding-agent 展示了如何把底层 Agent 能力工程化、产品化。
```
