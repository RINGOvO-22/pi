"""  总览: Qwen 流式 Tool Calling  """
"""
目标: 在 P5 文本流的基础上, 解析 Qwen streaming tool_calls。

P5 已处理:
    - delta.content
    - text_start / text_delta / text_end / done

P5B 新增处理:
    - delta.tool_calls
    - toolcall_start / toolcall_delta / toolcall_end

关键变化:
    OpenAI-compatible streaming 中, tool call 的 arguments 会分片返回。
    所以需要用 index 累积:
        id
        function.name
        function.arguments 字符串

最后再将完整 arguments 字符串 json.loads(...) 成 dict, 包装成 ToolCall。
"""

"""  1. 准备 api key / 基础依赖  """
import json
import os
import time
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from p1_types import (
    AssistantMessage,
    Context,
    TextContent,
    Tool,
    ToolCall,
    Usage,
    UserMessage,
)


def get_qwen_api_key() -> str:
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)

    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError(f"Missing QWEN_API_KEY in {env_path}")

    return api_key


def now_ms() -> int:
    return int(time.time() * 1000)


"""  2. 构造 Context 和 Tool  """
"""
这里复用 P6 的 list_project_tree 工具定义。
本文件先只练习 streaming tool_call 解析, 暂不执行工具。
"""

def create_tool() -> Tool:
    return Tool(
        name="list_project_tree",
        description="列出当前学习项目的文件目录结构。",
        parameters={
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "相对于项目根目录的路径, 默认使用 '.'。",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "目录深度, 默认 3, 最大 5。",
                    "minimum": 0,
                    "maximum": 5,
                },
            },
            "required": [],
        },
    )


def create_context() -> Context:
    return Context(
        system_prompt="我正在借该项目学习 agent 开发, 你是我的学习助手。",
        messages=[
            UserMessage(
                role="user",
                content=(
                    "请调用 list_project_tree 工具读取当前项目目录, "
                    "然后根据文件结构判断我现在完成了哪些学习阶段。"
                ),
                timestamp=now_ms(),
            )
        ],
        tools=[create_tool()],
    )


"""  3. Context / tools 转 OpenAI-compatible payload  """
"""
和 P6 相同:
    Context.messages -> messages
    Context.tools -> tools
"""

def context_to_openai_messages(context: Context) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []

    if context.system_prompt:
        messages.append({"role": "system", "content": context.system_prompt})

    for message in context.messages:
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                content = message.content
            else:
                content = "\n".join(
                    block.text for block in message.content if isinstance(block, TextContent)
                )
            messages.append({"role": "user", "content": content})

        elif isinstance(message, AssistantMessage):
            content = "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )
            tool_calls = [
                {
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.arguments, ensure_ascii=False),
                    },
                }
                for block in message.content if isinstance(block, ToolCall)
            ]

            payload: dict[str, object] = {"role": "assistant", "content": content}
            if tool_calls:
                payload["tool_calls"] = tool_calls
            messages.append(payload)

    return messages


def tools_to_openai_tools(tools: list[Tool]) -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


"""  4. 解析 streaming tool_call delta  """
"""
Qwen/OpenAI-compatible stream 中, 每个 chunk 可能包含:
    delta.content
    delta.tool_calls

delta.tool_calls 中的每个元素通常包含:
    index
    id
    function.name
    function.arguments 的一段字符串

需要按 index 累积, 最后再组装为 ToolCall。
"""

ToolCallState = dict[str, Any]


def parse_arguments(arguments_text: str) -> dict[str, Any]:
    try:
        value = json.loads(arguments_text or "{}")
    except json.JSONDecodeError:
        return {}

    if isinstance(value, dict):
        return value
    return {}


def state_to_tool_call(state: ToolCallState) -> ToolCall:
    return ToolCall(
        type="toolCall",
        id=str(state.get("id", "")),
        name=str(state.get("name", "")),
        arguments=parse_arguments(str(state.get("arguments_text", ""))),
    )


def call_qwen_stream_toolcall(
    api_key: str,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]],
) -> Iterator[dict[str, object]]:
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    partial_message = AssistantMessage(
        role="assistant",
        content=[],
        usage=Usage(),
        stop_reason="stop",
        timestamp=now_ms(),
        api="openai-completions",
        provider="qwen",
        model="qwen-plus",
    )

    # 1. start
    # assistant response 开始了. 此时 partial_message.content 为空列表.
    yield {"type": "start", "partial": partial_message}

    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        stream=True,
    )

    text_started = False
    text_so_far = ""
    tool_states: dict[int, ToolCallState] = {} 

    for chunk in response:
        delta = chunk.choices[0].delta

        # 1 处理 delta 中的文本
        text_delta = delta.content or ""
        if text_delta:
            if not text_started:
                partial_message.content.append(TextContent(type="text", text=""))
                text_started = True
                # 1.1 text_start
                # 第一次收到文本增量前, 先创建 TextContent 内容块.
                yield {
                    "type": "text_start",
                    "content_index": len(partial_message.content) - 1,
                    "partial": partial_message,
                }

            text_so_far += text_delta
            partial_message.content[0] = TextContent(type="text", text=text_so_far)
            # 1.2 text_delta
            # 每个 text_delta 表示模型又生成了一段文本.
            yield {
                "type": "text_delta",
                "content_index": 0,
                "delta": text_delta,
                "partial": partial_message,
            }

        # 2. 处理 delta 中的 tool calls
        for delta_tool_call in delta.tool_calls or []:
            # delta_tool_call 常见字段:
            #     index: 同一轮输出中的第几个 tool call, 用于分片归并.
            #     id: provider 生成的 tool call id, 后续 ToolResultMessage 要用它关联.
            #     type: 通常是 "function".
            #     function.name: 工具名.
            #     function.arguments: 工具参数 JSON 字符串的一段增量.

            tool_index = delta_tool_call.index or 0

            # 2.1 toolcall_start
            # 第一次看到某个 tool_call index 时, 创建一个 ToolCall 内容块占位. 
            if tool_index not in tool_states:
                content_index = len(partial_message.content)
                tool_states[tool_index] = {
                    "id": "",
                    "name": "",
                    "arguments_text": "",
                    "content_index": content_index,
                }
                partial_message.content.append(
                    ToolCall(type="toolCall", id="", name="", arguments={})
                )
                
                yield {
                    "type": "toolcall_start",
                    "content_index": content_index,
                    "partial": partial_message,
                }

            state = tool_states[tool_index]

            if delta_tool_call.id:
                state["id"] = delta_tool_call.id

            if delta_tool_call.function:
                if delta_tool_call.function.name:
                    state["name"] = delta_tool_call.function.name

                arguments_delta = delta_tool_call.function.arguments or ""
                if arguments_delta:
                    state["arguments_text"] += arguments_delta
                    # 2.2 toolcall_delta
                    # arguments 是分片返回的 JSON 字符串, 这里逐段累积.
                    yield {
                        "type": "toolcall_delta",
                        "content_index": state["content_index"],
                        "delta": arguments_delta,
                        "partial": partial_message,
                    }

            partial_message.content[state["content_index"]] = state_to_tool_call(state)

    if text_started:
        # 3. text_end
        # 文本流结束后, 发出完整文本内容.
        yield {
            "type": "text_end",
            "content_index": 0,
            "content": text_so_far,
            "partial": partial_message,
        }

    for tool_index in sorted(tool_states):
        state = tool_states[tool_index]
        tool_call = state_to_tool_call(state)
        partial_message.content[state["content_index"]] = tool_call
        # 4. toolcall_end
        # arguments 字符串累积完成后, 解析为 dict 并生成最终 ToolCall.
        yield {
            "type": "toolcall_end",
            "content_index": state["content_index"],
            "tool_call": tool_call,
            "partial": partial_message,
        }

    stop_reason = "toolUse" if tool_states else "stop"
    final_message = AssistantMessage(
        role="assistant",
        content=partial_message.content,
        usage=Usage(),
        stop_reason=stop_reason,
        timestamp=now_ms(),
        api="openai-completions",
        provider="qwen",
        model="qwen-plus",
    )

    # 8. done
    # 本次 assistant message 生成完成. done.message 可追加到 context.messages.
    yield {
        "type": "done",
        "reason": stop_reason,
        "message": final_message,
    }


"""  5. 消费 stream events  """
"""
这里重点观察 toolcall_* 事件。
最终 done.message 才是可以 append 到 context.messages 的 AssistantMessage。
"""

def consume_qwen_stream_toolcall(events: Iterator[dict[str, object]]) -> AssistantMessage:
    final_message: AssistantMessage | None = None

    for event in events:
        event_type = event["type"]

        if event_type == "text_delta":
            print(event["delta"], flush=True)

        elif event_type == "toolcall_start":
            print("[toolcall_start]")

        elif event_type == "toolcall_delta":
            print(f"[toolcall_delta] {event['delta']}")

        elif event_type == "toolcall_end":
            tool_call = event["tool_call"]
            if isinstance(tool_call, ToolCall):
                print("[toolcall_end]")
                print(json.dumps(asdict(tool_call), indent=2, ensure_ascii=False))

        elif event_type == "done":
            message = event["message"]
            if isinstance(message, AssistantMessage):
                final_message = message

    print()

    if final_message is None:
        raise RuntimeError("Qwen stream ended without done event")

    return final_message


"""  6. main: 验证 streaming tool_call 解析  """
"""
最终链路:
    Context + tools
        -> Qwen stream=True
        -> text/tool_call events
        -> AssistantMessage(ToolCall)
"""

if __name__ == "__main__":
    print("=" * 60, "\n1 API Key / 密钥")
    api_key = get_qwen_api_key()
    print("QWEN_API_KEY loaded")

    print("=" * 60, "\n2 Context / 上下文")
    context = create_context()
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))

    print("=" * 60, "\n3.1 OpenAI Messages / API 消息格式")
    openai_messages = context_to_openai_messages(context)
    print(json.dumps(openai_messages, indent=2, ensure_ascii=False))

    print("=" * 60, "\n3.2 OpenAI Tools / API 工具定义")
    openai_tools = tools_to_openai_tools(context.tools)
    print(json.dumps(openai_tools, indent=2, ensure_ascii=False))

    print("=" * 60, "\n4 Qwen Stream ToolCall Output / Qwen 流式工具调用输出")
    events = call_qwen_stream_toolcall(api_key, openai_messages, openai_tools)
    assistant_message = consume_qwen_stream_toolcall(events)

    print("=" * 60, "\n5 AssistantMessage / 助手消息")
    context.messages.append(assistant_message)
    print(json.dumps(asdict(assistant_message), indent=2, ensure_ascii=False))

    print("=" * 60, "\n6 ContextAfterAssistant / 追加助手消息后的上下文")
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))
    print("=" * 60)
