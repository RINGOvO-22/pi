"""  总览: 流式事件类型  """
"""
P8 中的 stream event 用来描述 assistant message 的生成过程。

静态结果:
    AssistantMessage

动态过程:
    AssistantMessageEvent

这些事件后续会由 qwen.py 产生, 由 agent_loop.py 消费。
"""

"""  1. AssistantMessageEvent 事件变体  """
"""
事件类型:
    start
    text_start
    text_delta
    text_end
    toolcall_start
    toolcall_delta
    toolcall_end
    done
    error

说明:
    text_delta 表示文本增量。
    toolcall_delta 表示工具参数 JSON 字符串还在逐段生成。
    done.message 是最终可以 append 到 context.messages 的 AssistantMessage。
"""
from typing import Literal, TypedDict

from .types import AssistantMessage, StopReason, ToolCall


class StartEvent(TypedDict):
    type: Literal["start"]
    partial: AssistantMessage


class TextStartEvent(TypedDict):
    type: Literal["text_start"]
    content_index: int
    partial: AssistantMessage


class TextDeltaEvent(TypedDict):
    type: Literal["text_delta"]
    content_index: int
    delta: str
    partial: AssistantMessage


class TextEndEvent(TypedDict):
    type: Literal["text_end"]
    content_index: int
    content: str
    partial: AssistantMessage


class ToolCallStartEvent(TypedDict):
    type: Literal["toolcall_start"]
    content_index: int
    partial: AssistantMessage


class ToolCallDeltaEvent(TypedDict):
    type: Literal["toolcall_delta"]
    content_index: int
    delta: str
    partial: AssistantMessage


class ToolCallEndEvent(TypedDict):
    type: Literal["toolcall_end"]
    content_index: int
    tool_call: ToolCall
    partial: AssistantMessage


class DoneEvent(TypedDict):
    type: Literal["done"]
    reason: StopReason
    message: AssistantMessage


class ErrorEvent(TypedDict):
    type: Literal["error"]
    reason: Literal["error", "aborted"]
    error: AssistantMessage


AssistantMessageEvent = (
    StartEvent
    | TextStartEvent
    | TextDeltaEvent
    | TextEndEvent
    | ToolCallStartEvent
    | ToolCallDeltaEvent
    | ToolCallEndEvent
    | DoneEvent
    | ErrorEvent
)
