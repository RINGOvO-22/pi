# 实践练习

本文件记录学习 Pi Agent 架构时可以做的小练习。

建议每读完一层，就做一个小练习，避免只读代码不动手。

## 练习 1：最小 LLM 调用

目标：理解 `packages/ai` 的基本用法。

实现一个脚本：

- 构造 context。
- 选择一个 model。
- 调用模型。
- 流式打印 assistant 输出。

重点理解：

```text
Context → stream → AssistantMessage
```

## 练习 2：最小 Agent

目标：理解 `packages/agent` 的基本用法。

实现一个最小 agent：

- 接收一条用户输入。
- 调用 Agent。
- 订阅事件。
- 把 assistant 的 text_delta 打印到终端。
- 暂时不加工具。

重点理解：

```text
prompt → agent_start → turn_start → message_update → message_end → agent_end
```

## 练习 3：添加 `get_time` 工具

目标：理解工具调用。

添加一个简单工具：

```text
get_time(timezone?)
```

让模型可以调用它获取当前时间。

重点理解：

```text
Tool schema → toolCall → execute → toolResult → next LLM turn
```

## 练习 4：实现 `read_file` 工具

目标：理解 Coding Agent 的雏形。

实现：

```text
read_file(path)
```

让 Agent 可以读取本地文件并基于文件内容回答问题。

重点理解：

- 工具输入参数校验。
- 工具结果如何放回上下文。
- 文件访问的安全边界。

## 练习 5：实现受限 bash 工具

目标：理解工具权限和安全控制。

实现：

```text
run_command(command)
```

但只允许执行：

```text
pwd
ls
grep
```

重点理解：

- 模型请求工具不等于工具一定会执行。
- `beforeToolCall` 可以做权限拦截。
- 工具失败应返回 tool error，而不是直接让 Agent Loop 崩溃。

## 练习 6：实现简单会话保存

目标：理解产品化 Agent 需要状态管理。

实现：

- 每次对话后保存 messages 到 JSON 文件。
- 下次启动时恢复 messages。
- 支持 continue。

重点理解：

```text
Agent Runtime + Session = 可持续工作的 Agent 应用
```

## 最终目标

通过这些练习，做出一个简化版 Coding Agent：

- 能和模型对话。
- 能调用本地工具。
- 能读取文件。
- 能受限执行命令。
- 能保存和恢复会话。

这就是一个真实 Agent 应用的最小闭环。
