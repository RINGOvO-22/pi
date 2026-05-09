"""  总览  """
"""
Phase 1: packages/ai/src/types.ts 类型提纲

目标: 先建立 `packages/ai` 的核心类型地图, 理解一次 LLM 调用需要哪些数据、模型返回什么数据、工具调用如何表达。

1. Provider / API 类型

    这组类型描述“模型来自哪里”以及“使用哪种底层 API 协议”。

    - Provider
        具体服务商或模型来源, 例如 openai / anthropic / google / qwen / ollama。

    - KnownProvider
        Pi 内置认识的 provider 列表。

    - Api
        模型实际使用的 API 协议类型。
        例如 OpenAI-compatible、Anthropic Messages、Google Generative AI 等。

    - KnownApi
        Pi 内置支持的 API 协议列表。

    重要说明:
        provider 不是 api。
        多个 provider 可能共用同一种 api, 例如很多服务都兼容 OpenAI Chat Completions。

2. Model / 模型类型

    Model 描述一个具体可调用的模型。

    - Model
        包含 id、name、provider、api、baseUrl、contextWindow、maxTokens、input、reasoning、cost 等信息。

    - ThinkingLevel / ModelThinkingLevel
        描述模型 reasoning / thinking 能力的控制级别。

    - Usage
        描述一次调用的 token 和 cost 使用情况。

    重要说明:
        Model 不只是模型名, 它还携带 provider、api、能力、价格、上下文窗口等元信息。
        上层调用时通过 Model 知道应该使用哪个 provider adapter。

3. Message / 消息类型

    Message 是 LLM 上下文中的基本单位。

    - Message
        总类型, 通常是 UserMessage | AssistantMessage | ToolResultMessage。

    - UserMessage
        用户输入的消息。

    - AssistantMessage
        模型返回的消息。
        它的 content 不是一个普通字符串, 而是多个内容块组成的列表。

    - ToolResultMessage
        工具执行完成后回填给模型的消息。

    - StopReason
        assistant 本次生成停止的原因。
        常见值: stop / length / toolUse / error / aborted。

    重要说明:
        stopReason == "toolUse" 通常表示模型请求调用工具, 上层需要执行工具并继续下一轮调用。

4. ContentBlock / Assistant 内容块类型

    AssistantMessage.content 是内容块列表, 用来表达文本、思考、图片、工具调用等不同内容。

    - ContentBlock
        内容块总称, 可理解为 TextContent | ThinkingContent | ImageContent | ToolCall。

    - TextContent
        普通文本输出。

    - ThinkingContent
        reasoning / thinking 内容。

    - ImageContent
        图片内容, 通常以 base64 + mimeType 表示。

    - ToolCall
        模型请求调用某个工具。
        包含 id、name、arguments。

    重要说明:
        assistant.content 设计成列表, 是为了支持同一条 assistant 消息中混合出现 text、thinking、toolCall 等内容。

5. Tool / 工具相关类型

    这组类型描述模型可以调用哪些外部能力, 以及调用结果如何返回。

    - Tool
        工具定义。
        通常包含 name、description、parameters。
        parameters 是工具参数 schema。

    - ToolCall
        模型产生的工具调用请求。
        表示“我要调用哪个工具, 参数是什么”。

    - ToolResultMessage
        程序真正执行工具后, 把结果作为消息返回给模型。

    重要说明:
        Tool 只是声明能力, 不负责执行。
        ToolCall 是模型的请求, 也不等于工具已经执行。
        ToolResultMessage 才是执行结果。

        关键关联字段:
            ToolCall.id <-> ToolResultMessage.toolCallId

6. Context / 调用上下文

    Context 是一次模型调用的输入。

    - Context
        通常包含 systemPrompt、messages、tools。

    结构可以理解为:
        Context = systemPrompt + messages + tools

    重要说明:
        Context 可以被序列化保存, 所以它是 session / conversation persistence 的基础。
        每次模型调用后, assistant message 或 tool result 会继续追加到 context.messages。

7. AssistantMessageEvent / 流式事件类型

    AssistantMessageEvent 描述模型流式生成过程中的事件。

    常见事件:
        - start
        - text_start
        - text_delta
        - text_end
        - thinking_start
        - thinking_delta
        - thinking_end
        - toolcall_start
        - toolcall_delta
        - toolcall_end
        - done
        - error

    重要说明:
        流式接口不是直接返回字符串, 而是不断产生事件。
        text_delta 表示文本增量。
        toolcall_delta 表示工具参数还在逐步生成。
        done 表示本次 assistant message 完成。
        error 表示出错或中止。

8. StreamOptions / 调用选项

    这组类型描述调用模型时的额外选项。

    - StreamOptions
        较底层、provider-specific 的调用选项。
        可能包含 apiKey、signal、temperature、maxTokens、sessionId 等。

    - SimpleStreamOptions
        更统一、更上层的简化选项。
        例如统一 reasoning 级别。

    重要说明:
        options 不属于消息上下文本身, 而是控制“这次怎么调用模型”。
        例如 apiKey、abort signal、reasoning 强度、缓存 sessionId 等。

Phase 1 最小必须掌握:
    - Model
    - Context
    - Message
    - AssistantMessage
    - Tool
    - ToolCall
    - ToolResultMessage
    - ContentBlock
    - StopReason
    - Usage

后续 Phase 2 会重点展开:
    - AssistantMessageEvent
    - stream / complete
    - provider event 到标准 event 的转换
"""

"""  顺序  """
"""
1. 内容块
2. 消息
3. 停止原因和用量
4. 上下文
5. 工具关系
6. 模型

说明:
    ToolCall 会在“内容块”和“工具关系”中重复出现。
    ToolResultMessage 会在“消息”和“工具关系”中重复出现。
"""

"""  源码阅读方法  """
"""
1. 该类型表示什么
2. 它属于哪里? 顶层元素or其他类型中的元素
3. 字段含义
4. python中如何实现
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
from dataclasses import dataclass # 用于简化"数据类"的定义
from typing import Literal, Any # Literal: 强制为某个值

@dataclass
class TextContent:
    type: Literal["text"] # llm 应用中常要做json序列化, 这样的方式能便于区分不同的 content 块(text, thinking, image, toolCall)
    text: str
    text_signature: str | None = None # 略, 详见源码

@dataclass
class ThinkingContent:
    type: Literal["thinking"]
    thinking: str
    thinking_signature: str | None = None
    # True 表示 thinking 内容被安全策略隐藏/打码。
    # 如果 provider 提供不透明/加密 payload, 通常放在 thinking_signature 里用于多轮连续性。
    redacted: bool | None = None

@dataclass
class ImageContent:
    type: Literal["image"]
    data: str # base64 encoded image data
    mime_type: str # e.g., "image/jpeg", "image/png"

@dataclass
class ToolCall:
    type: Literal["toolCall"]
    id: str # 本次工具调用 id. 后面 ToolResultMessage 要用它关联.
    name: str # 工具名
    arguments: dict[str, Any] # 模型生成的工具参数
    thought_signature: str | None = None # Google相关元数据. 略

"""  2. 消息  """
"""
对应源码中的类型:
    UserMessage, AssistantMessage, ToolResultMessage, Message

说明:
    Message = UserMessage | AssistantMessage | ToolResultMessage

消息对象类型标识:
    "role" 字段: "user" | "assistant" | "toolResult"
"""
from dataclasses import field

@dataclass
class UserMessage:
    role: Literal["user"]
    content: str | list[TextContent | ImageContent] # 2种形式: 普通 str or 内容块列表
    timestamp: int # Unix timestamp in milliseconds. 可选: 设置默认值: 当前时间戳.

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
    content: list[TextContent | ThinkingContent | ToolCall] # 重要. 后面会被用于判断是否有 ToolCall
    usage: Usage
    stop_reason: StopReason # 重要. 判断是否为 "toolUse"
    timestamp: int
    api: str = "" # 暂不设置
    provider: str = "" # 暂不设置
    model: str = "" # 暂不设置
    response_model: str | None = None # 略
    response_id: str | None = None # 略
    error_message: str | None = None # 略
    diagnostics: list[Any] | None = None # 略

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
"""

"""  4. 上下文  """
"""
对应源码中的类型:
    Context

说明:
    Context = systemPrompt + messages + tools
"""

"""  5. 工具关系  """
"""
对应源码中的类型:
    Tool, ToolCall, ToolResultMessage

说明:
    Tool 定义工具能力。
    ToolCall 是模型请求调用工具。
    ToolResultMessage 是程序执行工具后的结果。

关键关联字段:
    ToolCall.id <-> ToolResultMessage.toolCallId
"""

"""  6. 模型  """
"""
对应源码中的类型:
    Model

说明:
    Model 描述一个具体可调用的模型, 包括 id、provider、api、baseUrl、contextWindow、maxTokens、input、reasoning、cost 等。
"""
