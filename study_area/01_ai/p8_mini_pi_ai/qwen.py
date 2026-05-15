"""  总览: Qwen provider adapter  """
"""
目标: 调用 Qwen OpenAI-compatible streaming API, 并转成 mini_pi_ai 的 AssistantMessageEvent。

来源:
    迁移 P5B 的 streaming text/tool_call 解析逻辑。

三个主函数:
    get_qwen_api_key(): 从 .env 读取 QWEN_API_KEY。
    stream_qwen(api_key, messages, tools): 调用 Qwen stream=True, 产出 AssistantMessageEvent。
    usage_from_qwen_response(response): 后续非流式备用, 当前 streaming 暂不使用。
"""

"""  1. 准备 api key / 基础依赖  """
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .stream import AssistantMessageEvent
from .types import AssistantMessage, TextContent, ToolCall, Usage


def find_project_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "AGENTS.md").exists() and (path / "package.json").exists():
            return path

    return start


def get_qwen_api_key() -> str:
    project_root = find_project_root(Path(__file__).resolve())
    env_path = project_root / ".env"
    load_dotenv(env_path)

    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError(f"Missing QWEN_API_KEY in {env_path}")

    return api_key


def now_ms() -> int:
    return int(time.time() * 1000)


"""  2. streaming tool_call 解析 helpers  """
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


"""  3. stream_qwen  """
"""
调用 Qwen stream=True, 并把 provider chunk 转成统一 AssistantMessageEvent。

输出事件:
    start
    text_start
    text_delta
    text_end
    toolcall_start
    toolcall_delta
    toolcall_end
    done
"""

def stream_qwen(
    api_key: str,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]],
) -> Iterator[AssistantMessageEvent]:
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

    yield {"type": "start", "partial": partial_message}

    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        stream=True,
        stream_options={"include_usage": True}, # 为了获取 Usage
    )

    stream_usage = Usage() # 初始化 usage 记录
    text_started = False
    text_so_far = ""
    tool_states: dict[int, ToolCallState] = {}

    for chunk in response:
        # 如果当前 chunk 携带 usage, 记录 token 用量并继续处理后续 chunk. (通常只在最后一个chunk有)
        if chunk.usage:
            stream_usage = Usage(
                input=chunk.usage.prompt_tokens or 0,
                output=chunk.usage.completion_tokens or 0,
                cache_read=0,
                cache_write=0,
                total_tokens=chunk.usage.total_tokens or 0,
            )
            continue

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        text_delta = delta.content or ""
        if text_delta:
            if not text_started:
                partial_message.content.append(TextContent(type="text", text=""))
                text_started = True
                # 2. text_start
                # 第一次收到文本增量前, 先创建 TextContent 内容块.
                yield {
                    "type": "text_start",
                    "content_index": len(partial_message.content) - 1,
                    "partial": partial_message,
                }

            text_so_far += text_delta
            partial_message.content[0] = TextContent(type="text", text=text_so_far)
            # 3. text_delta
            # 每个 text_delta 表示模型又生成了一段文本.
            yield {
                "type": "text_delta",
                "content_index": 0,
                "delta": text_delta,
                "partial": partial_message,
            }

        for delta_tool_call in delta.tool_calls or []:
            # delta_tool_call 常见字段:
            #     index: 同一轮输出中的第几个 tool call, 用于分片归并.
            #     id: provider 生成的 tool call id, 后续 ToolResultMessage 要用它关联.
            #     type: 通常是 "function".
            #     function.name: 工具名.
            #     function.arguments: 工具参数 JSON 字符串的一段增量.
            tool_index = delta_tool_call.index or 0

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
                # 4. toolcall_start
                # 第一次看到某个 tool_call index 时, 创建一个 ToolCall 内容块占位.
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
                    # 5. toolcall_delta
                    # arguments 是分片返回的 JSON 字符串, 这里逐段累积.
                    yield {
                        "type": "toolcall_delta",
                        "content_index": state["content_index"],
                        "delta": arguments_delta,
                        "partial": partial_message,
                    }

            partial_message.content[state["content_index"]] = state_to_tool_call(state)

    if text_started:
        # 6. text_end
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
        # 7. toolcall_end
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
        usage=stream_usage,
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


"""  4. usage_from_qwen_response  """
"""
非流式备用函数。
当前 P8 以 streaming 为主, 暂时不会用到。
"""

def usage_from_qwen_response(response) -> Usage:
    usage = response.usage
    if usage is None:
        return Usage()

    return Usage(
        input=usage.prompt_tokens or 0,
        output=usage.completion_tokens or 0,
        cache_read=0,
        cache_write=0,
        total_tokens=usage.total_tokens or 0,
    )
