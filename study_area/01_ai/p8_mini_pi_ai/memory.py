"""  总览: Context memory / 上下文持久化  """
"""
目标: 把 Context 保存到 JSON, 并在下次启动时恢复。

来源:
    迁移 P7 的反序列化 helpers 和 load/save 逻辑。

职责边界:
    memory.py 只负责 JSON <-> Context。
    create_context / append_user_message 后续放到 main.py / agent_loop.py。

两个主函数:
    load_context(path): 从 JSON 文件读取并恢复 Context; 文件不存在或为空时返回 None。
    save_context(context, path): 将 Context 转成 dict, 再保存为 JSON 文件。
"""

"""  1. 准备路径 / 基础依赖  """
"""
记忆文件:
    study_area/01_ai/p8_mini_pi_ai/context_memory.json
"""
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .types import (
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

空文件处理:
    文件不存在 -> None
    文件为空 -> None
    文件有 JSON -> Context
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
