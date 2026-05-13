"""  总览: Context / tools 转 OpenAI-compatible payload  """
"""
目标: 把 mini_pi_ai 的内部统一类型转成 Qwen/OpenAI-compatible API 能接受的格式。

主要转换:
    Context.messages -> messages
    Context.tools -> tools

来源:
    直接复用 P6 的转换逻辑。
"""

"""  1. Context.messages -> OpenAI-compatible messages  """
"""
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
import json

from .types import (
    AssistantMessage,
    Context,
    TextContent,
    Tool,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


def context_to_openai_messages(context: Context) -> list[dict[str, object]]:
    """
    直接复用 P6 的函数定义。
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

        # 3. assistant message
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
                "content": content,
            }

            if tool_calls:
                assistant_payload["tool_calls"] = tool_calls

            messages.append(assistant_payload)

        # 4. tool result message
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


"""  2. Context.tools -> OpenAI-compatible tools  """
"""
Tool 只是内部统一类型。
发送给 Qwen 时, 需要转成 OpenAI-compatible function tool 格式。
"""

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
