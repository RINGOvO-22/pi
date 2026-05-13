"""  总览: 静态核心类型  """
"""
Phase 8: mini pi ai 的核心类型。

本文件从 P1 复制核心 dataclass, 让 p8_mini_pi_ai 成为一个相对独立的小项目。

P8 重点不是重新设计类型, 而是用这些类型串起:
    - memory
    - stream
    - tool calling
    - agent loop
"""

"""  顺序  """
"""
1. 内容块
2. 消息
3. 停止原因和用量
4. 上下文
5. 工具关系
6. 模型
"""

"""  1. 内容块  """
"""
对应源码中的类型:
    TextContent, ThinkingContent, ImageContent, ToolCall

说明:
    这些类型描述消息 content 中的内容块；其中 TextContent / ThinkingContent / ToolCall 常用于 AssistantMessage.content，TextContent / ImageContent 也可用于 UserMessage 或 ToolResultMessage 的 content。

内容块类型标识:
    "type" 字段: "text" | "thinking" | "image" | "toolCall"
"""
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TextContent:
    type: Literal["text"]
    text: str
    text_signature: str | None = None


@dataclass
class ThinkingContent:
    type: Literal["thinking"]
    thinking: str
    thinking_signature: str | None = None
    redacted: bool | None = None


@dataclass
class ImageContent:
    type: Literal["image"]
    data: str
    mime_type: str


@dataclass
class ToolCall:
    type: Literal["toolCall"]
    id: str
    name: str
    arguments: dict[str, Any]
    thought_signature: str | None = None


"""  2. 消息  """
"""
对应源码中的类型:
    UserMessage, AssistantMessage, ToolResultMessage, Message

说明:
    Message = UserMessage | AssistantMessage | ToolResultMessage

消息对象类型标识:
    "role" 字段: "user" | "assistant" | "toolResult"
"""

@dataclass
class UserMessage:
    role: Literal["user"]
    content: str | list[TextContent | ImageContent]
    timestamp: int


@dataclass
class Cost:
    input: float = 0
    output: float = 0
    cache_read: float = 0
    cache_write: float = 0
    total: float = 0


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: Cost = field(default_factory=Cost)


StopReason = Literal["stop", "length", "toolUse", "error", "aborted"]


@dataclass
class AssistantMessage:
    role: Literal["assistant"]
    content: list[TextContent | ThinkingContent | ToolCall]
    usage: Usage
    stop_reason: StopReason
    timestamp: int
    api: str = ""
    provider: str = ""
    model: str = ""
    response_model: str | None = None
    response_id: str | None = None
    error_message: str | None = None
    diagnostics: list[Any] | None = None


@dataclass
class ToolResultMessage:
    role: Literal["toolResult"]
    tool_call_id: str
    tool_name: str
    content: list[TextContent | ImageContent]
    is_error: bool
    timestamp: int
    details: Any | None = None


Message = UserMessage | AssistantMessage | ToolResultMessage

"""  3. 停止原因和用量  """
"""
对应源码中的类型:
    StopReason, Usage

说明:
    StopReason 描述 assistant 为什么停止。
    Usage 描述 token / cost 使用情况。

被使用的位置:
    均为 AssistantMessage 中的字段值
"""

# 在 section 2 中作为依赖类已定义.

"""  4. 上下文  """
"""
对应源码中的类型:
    Context

说明:
    Context = systemPrompt + messages + tools
"""

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Context:
    messages: list[Message] = field(default_factory=list)
    system_prompt: str | None = None
    tools: list[Tool] = field(default_factory=list)


"""  5. 工具关系  """
"""
对应源码中的类型:
    Tool, ToolCall, ToolResultMessage

说明:
    Tool 定义工具能力。
    ToolCall 是模型请求调用工具。
    ToolResultMessage 是程序执行工具后的结果。

关键关联字段:
    ToolCall.id <-> ToolResultMessage.tool_call_id
"""

# 已于 section 1, 2, 4 完成定义. 该 section 是为了关系串联及梳理.

"""  6. 模型  """
"""
对应源码中的类型:
    Model

说明:
    Model 描述一个具体可调用的模型, 包括 id、provider、api、baseUrl、contextWindow、maxTokens、input、reasoning、cost 等。

重点:
    provider 不是 api。
    例如 Qwen 可以是 provider="qwen", api="openai-completions"。
"""

@dataclass
class ModelCost:
    input: float = 0
    output: float = 0
    cache_read: float = 0
    cache_write: float = 0


@dataclass
class Model:
    id: str
    name: str
    provider: str
    api: str
    base_url: str

    reasoning: bool = False
    input: list[Literal["text", "image"]] = field(default_factory=lambda: ["text"])
    thinking_level_map: dict[str, str | None] | None = None

    cost: ModelCost = field(default_factory=ModelCost)
    context_window: int = 0
    max_tokens: int = 0

    headers: dict[str, str] | None = None
    compat: Any | None = None
