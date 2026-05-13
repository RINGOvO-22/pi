# P8 mini_pi_ai

目标: 把 P1-P7 的能力合成一个最小 agent 框架。

核心能力:

```text
Context memory
+ Qwen streaming
+ tool calling
+ agent loop
```

## 使用说明

从 `study_area/01_ai` 目录用模块方式运行:

```bash
cd /home/djh/workspace/pi/study_area/01_ai
python -m p8_mini_pi_ai.main
```

交互模式:

```text
user: 你的输入
assistant: 模型回复
```

退出命令:

```text
q
quit
exit
```

运行后会更新:

```text
p8_mini_pi_ai/context_memory.json
p8_mini_pi_ai/last_response.md
```

注意:
    不要直接运行 `python p8_mini_pi_ai/main.py`, 需要用 `python -m p8_mini_pi_ai.main`。

## 开发顺序

### 1. `types.py` - 核心类型

文件跳转: [`types.py`](types.py)

定义静态数据结构:

```text
Context
Message
UserMessage
AssistantMessage
ToolResultMessage
TextContent
ToolCall
Tool
Usage
Model
```

作用: 描述 agent 的状态、模型输入输出、工具调用和工具结果。

---

### 2. `stream.py` - 流式事件

文件跳转: [`stream.py`](stream.py)

定义动态生成过程中的事件:

```text
start
text_start
text_delta
text_end
toolcall_start
toolcall_delta
toolcall_end
done
error
```

作用: 把 provider 的流式 chunk 转成统一事件, 方便 UI、日志、agent loop 消费。

---

### 3. `context.py` - Context 转 provider payload

文件跳转: [`context.py`](context.py)

实现转换函数:

```text
Context.messages -> OpenAI-compatible messages
Context.tools -> OpenAI-compatible tools
```

作用: 把内部统一类型转成 Qwen/OpenAI-compatible API 能接受的格式。

---

### 4. `memory.py` - 上下文持久化

文件跳转: [`memory.py`](memory.py)

实现:

```text
save_context
load_context
dict_to_context
dict_to_message
dict_to_content_block
```

作用: 把 Context 保存到 JSON, 下次启动时恢复对话记忆。

---

### 5. `tools.py` - 本地工具

文件跳转: [`tools.py`](tools.py)

实现工具定义和执行:

```text
create_tools
list_project_tree
execute_tool_call
```

作用: 把模型产生的 ToolCall 转成真实 Python 函数调用, 再返回 ToolResultMessage。

---

### 6. `qwen.py` - Qwen provider adapter

文件跳转: [`qwen.py`](qwen.py)

实现 Qwen 调用:

```text
get_qwen_api_key
stream_qwen
parse streaming text/tool_calls
```

作用: 把 Qwen 的 OpenAI-compatible streaming response 转成 `AssistantMessageEvent`。

---

### 7. `agent_loop.py` - Agent 主循环

文件跳转: [`agent_loop.py`](agent_loop.py)

实现最小 agent loop:

```text
append user message
while True:
    stream model events
    append assistant message
    if no tool calls:
        break
    execute tools
    append tool results
save context
```

作用: 连接 memory、model、tools, 形成真正的 agent 行为。

---

### 8. `main.py` - 命令入口

文件跳转: [`main.py`](main.py)

实现运行入口:

```text
load/create context
run agent loop
print final context
```

作用: 作为 P8 的可运行 demo。

## 最终结构

```text
p8_mini_pi_ai/
├── README.md
├── __init__.py
├── types.py
├── stream.py
├── context.py
├── memory.py
├── tools.py
├── qwen.py
├── agent_loop.py
└── main.py
```

## 最终目标

```text
用户输入
  -> Context memory
  -> Qwen streaming
  -> ToolCall
  -> Python tool execution
  -> ToolResultMessage
  -> Qwen final answer
  -> save memory
```
