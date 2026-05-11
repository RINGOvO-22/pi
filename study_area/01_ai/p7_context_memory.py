"""  总览: Context Memory + Qwen Complete / 上下文记忆 + 真实模型调用  """
"""
目标: 实现一个最小可恢复的 Qwen 对话记忆。

核心流程:
    1. 准备 api key / 路径 / 基础依赖
    2. load_context: 如果已有记忆文件, 从 JSON 恢复 Context
    3. create_context: 如果没有记忆文件, 创建初始 Context
    4. 追加新的 UserMessage
    5. Context -> OpenAI-compatible messages
    6. 调用 Qwen 非流式 complete
    7. response -> AssistantMessage
    8. append AssistantMessage 到 context.messages
    9. save_context: 保存 Context 到 JSON 文件
    10. 打印 Context

本阶段重点:
    - 理解 Context 如何作为 memory/session 保存
    - 理解 JSON -> dataclass 恢复需要依赖 role/type 字段
    - 理解每轮模型调用后都要更新并保存 Context
"""

"""  1. 准备 api key / 路径 / 基础依赖  """
"""
复用 P4 的 .env 读取方式。

记忆文件:
    study_area/01_ai/context_memory.json
"""
import json
import os
import time
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
    ToolResultMessage,
    Usage,
    UserMessage,
)

MEMORY_PATH = Path(__file__).with_name("context_memory.json")


def get_qwen_api_key() -> str:
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)

    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError(f"Missing QWEN_API_KEY in {env_path}")

    return api_key


def now_ms() -> int:
    return int(time.time() * 1000)

"""  2. Context 反序列化 helpers  """
"""
分析:
    Context 保存: 直接用 asdict(Context) 即可将其转为 dict, 然后可用 JSON 导出.
    Context 读取: JSON 只保存普通 dict/list, 不保存 Python class 信息。

恢复时需要根据:
    message["role"]
    content_block["type"]

还原为:
    UserMessage
    AssistantMessage
    ToolResultMessage
    TextContent
    ToolCall

和 TypeScript 源码的区别:
    packages/ai 里 Message/Context 是 interface, 运行时没有 class。
    所以 TS 中 JSON.parse(...) 后, 只要对象结构符合即可当作 Context 使用。
    Python 这里使用 dataclass, json.loads(...) 只会得到 dict, 因此需要手动恢复成对应 dataclass。
"""
def dict_to_text_content(data: dict[str, Any]) -> TextContent:
    return TextContent(
        type="text",
        text=data.get("text", ""),
        text_signature=data.get("text_signature"),
    )


def dict_to_tool_call(data: dict[str, Any]) -> ToolCall:
    return ToolCall(
        type="toolCall",
        id=data.get("id", ""),
        name=data.get("name", ""),
        arguments=data.get("arguments", {}),
        thought_signature=data.get("thought_signature"),
    )


def dict_to_content_block(data: dict[str, Any]):
    block_type = data.get("type")

    if block_type == "text":
        return dict_to_text_content(data)
    if block_type == "toolCall":
        return dict_to_tool_call(data)

    raise ValueError(f"Unsupported content block type: {block_type}")


def dict_to_usage(data: dict[str, Any]) -> Usage:
    return Usage(
        input=data.get("input", 0),
        output=data.get("output", 0),
        cache_read=data.get("cache_read", 0),
        cache_write=data.get("cache_write", 0),
        total_tokens=data.get("total_tokens", 0),
    )


def dict_to_message(data: dict[str, Any]):
    role = data.get("role")

    if role == "user":
        raw_content = data.get("content", "")
        if isinstance(raw_content, list):
            content = [dict_to_content_block(block) for block in raw_content]
        else:
            content = raw_content

        return UserMessage(
            role="user",
            content=content,
            timestamp=data.get("timestamp", 0),
        )

    if role == "assistant":
        return AssistantMessage(
            role="assistant",
            content=[dict_to_content_block(block) for block in data.get("content", [])],
            usage=dict_to_usage(data.get("usage", {})),
            stop_reason=data.get("stop_reason", "stop"),
            timestamp=data.get("timestamp", 0),
            api=data.get("api", ""),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            response_model=data.get("response_model"),
            response_id=data.get("response_id"),
            error_message=data.get("error_message"),
            diagnostics=data.get("diagnostics"),
        )

    if role == "toolResult":
        return ToolResultMessage(
            role="toolResult",
            tool_call_id=data.get("tool_call_id", ""),
            tool_name=data.get("tool_name", ""),
            content=[dict_to_content_block(block) for block in data.get("content", [])],
            is_error=data.get("is_error", False),
            timestamp=data.get("timestamp", 0),
            details=data.get("details"),
        )

    raise ValueError(f"Unsupported message role: {role}")


def dict_to_tool(data: dict[str, Any]) -> Tool:
    return Tool(
        name=data.get("name", ""),
        description=data.get("description", ""),
        parameters=data.get("parameters", {}),
    )


def dict_to_context(data: dict[str, Any]) -> Context:
    return Context(
        messages=[dict_to_message(message) for message in data.get("messages", [])],
        system_prompt=data.get("system_prompt"),
        tools=[dict_to_tool(tool) for tool in data.get("tools", [])],
    )

"""  3. load_context / save_context  """
"""
save_context:
    Context(dataclass)
        -> asdict(context)
        -> JSON 文件

load_context:
    JSON 文件
        -> dict
        -> Context(dataclass)
"""

def save_context(context: Context, path: Path = MEMORY_PATH) -> None:
    path.write_text(
        json.dumps(asdict(context), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_context(path: Path = MEMORY_PATH) -> Context | None:
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None

    data = json.loads(text)
    return dict_to_context(data)

"""  4. create_context / append_user_message  """
"""
如果没有记忆文件, 创建初始 Context。

每次运行脚本时, 追加一条新的 UserMessage, 模拟继续对话。
"""
def create_context() -> Context:
    """
    与 load_context() 一致, 不追加此次的用户信息, 后面统一添加.
    """
    return Context(
        system_prompt="我们现在在学习 agent 开发, 你是我的学习助手. 我们学习小组除了我和你暂时没有其他成员."
    )

def append_user_message(context: Context, content: str) -> None:
    """
    简单起见, 这里 content 只传 str
    """
    context.messages.append(
        UserMessage(
            role="user",
            content=content,
            timestamp=now_ms()
        )
    )

"""  5. Context -> OpenAI-compatible messages  """
"""
复用 P6 的转换逻辑。

支持:
    - system_prompt
    - UserMessage(str)
    - AssistantMessage(TextContent)
    - AssistantMessage(ToolCall)
    - ToolResultMessage

暂时不处理:
    - ImageContent
    - ThinkingContent
"""

def context_to_openai_messages(context: Context) -> list[dict[str, object]]:
    """
    直接复用 p6 的函数定义
    """
    messages: list[dict[str, object]] = []

    # 1. system prompt
    if context.system_prompt:
        messages.append({
            "role": "system",
            "content": context.system_prompt,
        })

    for message in context.messages:
        # 2. user message

        # Recall: UserMessage 的 content 由两种形态: str | 内容块列表(文本 or 图像)
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                content = message.content
            else:
                content = "\n".join(
                    block.text for block in message.content if isinstance(block, TextContent)
                )
            messages.append({"role": "user", "content": content})

        # 3. assistant mesage

        # Recall: AssistantMessage 的 content 为内容块列表(文本/Thinking/ToolCall)
        elif isinstance(message, AssistantMessage):
            content = "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )

            # assistant message 中可能包含 ToolCall 内容块
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

            assistant_payload: dict[str, object] = {
                "role": "assistant", 
                "content": content
            }

            if tool_calls:
                assistant_payload["tool_calls"] = tool_calls
            
            messages.append(assistant_payload)
            
        # 4. 处理 ToolResultMessage
        elif isinstance(message, ToolResultMessage):
            content = "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )

            messages.append({
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": content,
            })

    return messages

"""  6. 调用 Qwen 非流式 complete  """
"""
复用 P4 的调用逻辑:
    OpenAI-compatible messages
        -> Qwen chat completions
        -> assistant text + usage
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


def call_qwen_complete(api_key: str, messages: list[dict[str, object]]) -> tuple[str, Usage]:
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
    )

    text = response.choices[0].message.content or ""
    usage = usage_from_qwen_response(response)
    return text, usage

"""  7. response -> AssistantMessage  """
"""
直接复用 P4 中的函数
将 Qwen 返回的文本和 usage 包装成统一 AssistantMessage。
"""

def create_assistant_message_from_text(text: str, usage: Usage) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextContent(type="text", text=text)],
        usage=usage,
        stop_reason="stop",
        timestamp=now_ms(),
        api="openai-completions",
        provider="qwen",
        model="qwen-plus",
    )

"""  8. main: 串起 memory loop  """
"""
最终链路:
    load/create Context
        -> append UserMessage
        -> call Qwen
        -> append AssistantMessage
        -> save Context
        -> print Context

这就是最小 session memory。

当前验证完整 Step 1-8:
    - 读取 API key
    - 尝试从记忆文件恢复 Context
    - 如果没有记忆文件, 创建新的 Context
    - 追加新的 UserMessage
    - 转换 OpenAI-compatible messages
    - 调用 Qwen
    - 构造并追加 AssistantMessage
    - 保存 Context
"""

if __name__ == "__main__":
    print("=" * 60, "\n1. API Key / 密钥")
    api_key = get_qwen_api_key()
    print("QWEN_API_KEY loaded")

    print("=" * 60, "\n3.1 Load Context / 读取上下文记忆(无则返回None)")
    loaded_context = load_context()
    if loaded_context is None:
        print(f"No memory file found: {MEMORY_PATH}")
    else:
        print(json.dumps(asdict(loaded_context), indent=2, ensure_ascii=False))

    print("=" * 60, "\n4.1 Context / 当前上下文(读取或初始化)")
    context = loaded_context or create_context()
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))

    print("=" * 60, "\n4.2 Append UserMessage / 追加用户消息")
    append_user_message(
        context,
        "我们的学习小组在上一次的基础上, 最近又新加入了一个成员, 请你简单统计下现在一共有几个人了?",
    )
    print(json.dumps(asdict(context.messages[-1]), indent=2, ensure_ascii=False))

    print("=" * 60, "\n5. ContextToOpenAIMessages / 上下文转 API 消息格式")
    openai_messages = context_to_openai_messages(context)
    print(json.dumps(openai_messages, indent=2, ensure_ascii=False))

    print("=" * 60, "\n6.1 QwenAssistantText / Qwen 助手文本")
    assistant_text, usage = call_qwen_complete(api_key, openai_messages)
    print(json.dumps(assistant_text, indent=2, ensure_ascii=False))

    print("=" * 60, "\n6.2 QwenUsage / Qwen 用量")
    print(json.dumps(asdict(usage), indent=2, ensure_ascii=False))

    print("=" * 60, "\n7. AssistantMessage / 助手消息")
    assistant_message = create_assistant_message_from_text(assistant_text, usage)
    context.messages.append(assistant_message)
    print(json.dumps(asdict(assistant_message), indent=2, ensure_ascii=False))

    print("=" * 60, "\n3.2 Save Context / 保存上下文记忆")
    save_context(context)
    print(f"Saved to: {MEMORY_PATH}")

    print("=" * 60, "\n8. ContextMemory / 当前记忆内容")
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))
    print("=" * 60)
