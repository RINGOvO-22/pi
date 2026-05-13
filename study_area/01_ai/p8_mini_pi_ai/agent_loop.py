"""  总览: Agent 主循环  """
"""
目标: 把 Context、Qwen streaming、ToolCall、ToolResultMessage 串成最小 agent loop。

核心流程:
    append UserMessage
    while True:
        Context -> OpenAI messages
        tools -> OpenAI tools
        stream_qwen(...)
        consume events -> AssistantMessage
        append AssistantMessage
        if no ToolCall:
            break
        execute tools
        append ToolResultMessage

职责边界:
    agent_loop.py 负责运行循环。
    memory.py 负责保存/读取。
    main.py 负责创建初始 Context 和入口编排。
"""

"""  1. 基础依赖  """
import json
import time
from collections.abc import Iterator
from dataclasses import asdict

from .context import context_to_openai_messages, tools_to_openai_tools
from .qwen import stream_qwen
from .stream import AssistantMessageEvent
from .tools import execute_tool_call
from .types import AssistantMessage, Context, TextContent, ToolCall, UserMessage


def now_ms() -> int:
    return int(time.time() * 1000)


"""  2. append_user_message  """
"""
每次用户输入都要追加到 Context.messages。
Context 就是 agent 的 session state。
"""

def append_user_message(context: Context, content: str) -> None:
    context.messages.append(
        UserMessage(
            role="user",
            content=content,
            timestamp=now_ms(),
        )
    )


"""  3. consume_events  """
"""
消费 Qwen streaming events。

职责:
    - text_delta: 实时打印文本
    - toolcall_start/toolcall_delta/toolcall_end: 打印工具调用过程
    - done: 取出最终 AssistantMessage

注意:
    done.message 才是可以 append 到 context.messages 的最终消息。
"""

def consume_events(events: Iterator[AssistantMessageEvent], verbose: bool = True) -> AssistantMessage:
    final_message: AssistantMessage | None = None

    for event in events:
        event_type = event["type"]

        if event_type == "text_delta":
            print(event["delta"], end="", flush=True)

        elif verbose and event_type == "toolcall_start":
            print("[toolcall_start]")

        elif verbose and event_type == "toolcall_delta":
            print(f"[toolcall_delta] {event['delta']}")

        elif verbose and event_type == "toolcall_end":
            print("[toolcall_end]")
            print(json.dumps(asdict(event["tool_call"]), indent=2, ensure_ascii=False))

        elif event_type == "done":
            final_message = event["message"]

    print()

    if final_message is None:
        raise RuntimeError("Qwen stream ended without done event")

    return final_message


"""  4. get_tool_calls  """
"""
从 AssistantMessage.content 中提取 ToolCall。
如果没有 ToolCall, 说明本轮是最终回答。
"""

def get_tool_calls(message: AssistantMessage) -> list[ToolCall]:
    return [block for block in message.content if isinstance(block, ToolCall)]


"""  5. run_agent_loop  """
"""
运行最小 agent loop。

循环含义:
    assistant message 是模型动作。
    ToolCall 是模型请求调用外部工具。
    ToolResultMessage 是环境观察结果。
    没有 ToolCall 时, agent 结束。
"""

def run_agent_loop(api_key: str, context: Context, max_turns: int = 5, verbose: bool = True) -> Context:
    for turn_index in range(max_turns):
        if verbose:
            print("=" * 60, f"\n7.{turn_index + 1}.1 OpenAI Messages / API 消息格式")
        openai_messages = context_to_openai_messages(context)
        if verbose:
            print(json.dumps(openai_messages, indent=2, ensure_ascii=False))

        if verbose:
            print("=" * 60, f"\n7.{turn_index + 1}.2 OpenAI Tools / API 工具定义")
        openai_tools = tools_to_openai_tools(context.tools)
        if verbose:
            print(json.dumps(openai_tools, indent=2, ensure_ascii=False))

        if verbose:
            print("=" * 60, f"\n7.{turn_index + 1}.3 Qwen Stream / Qwen 流式输出")
        events = stream_qwen(api_key, openai_messages, openai_tools)
        assistant_message = consume_events(events, verbose=verbose)
        context.messages.append(assistant_message)

        if verbose:
            print("=" * 60, f"\n7.{turn_index + 1}.4 AssistantMessage / 助手消息")
            print(json.dumps(asdict(assistant_message), indent=2, ensure_ascii=False))

        tool_calls = get_tool_calls(assistant_message)
        if not tool_calls:
            return context

        tool_results = [execute_tool_call(tool_call) for tool_call in tool_calls]
        if verbose:
            print("=" * 60, f"\n7.{turn_index + 1}.5 ToolResults / 工具执行结果")
            print(json.dumps([asdict(tool_result) for tool_result in tool_results], indent=2, ensure_ascii=False))

        for tool_result in tool_results:
            context.messages.append(tool_result)

    raise RuntimeError(f"Agent loop exceeded max_turns={max_turns}")
