"""  总览: Qwen 非流式调用  """
"""
目标: 从 fake model 进入真实模型调用，但先不做 stream、不做 tool calling

最小流程:
    1. 从环境变量读取 QWEN_API_KEY
    2. 构造 Context
    3. 把 Context.messages 转成 OpenAI-compatible messages
    4. 调用 Qwen chat completions
    5. 解析 response, 构造 AssistantMessage
    6. append 到 context.messages
"""

"""  1. 准备 api key  """
import os
from pathlib import Path

from dotenv import load_dotenv


def get_qwen_api_key() -> str:
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)

    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError("Missing QWEN_API_KEY in study_area/01_ai/.env")

    return api_key

"""  2. 构造 Context  """
"""
根据之前定义好的 Context 类的结构来构造
"""
from p1_types import AssistantMessage, Context, TextContent, UserMessage
import time


def now_ms() -> int:
    return int(time.time() * 1000)


def create_context() -> Context:
    return Context(
        system_prompt="我们现在在学习 agent 开发, 你是助手.",
        messages=[
            UserMessage(
                role="user",
                content="请你给我一些建议. 100字以内.",
                timestamp=now_ms(),
            )
        ],
    )

"""  3. 转换 Context 为 API 所需格式"""
"""
Qwen / OpenAI-compatible API 所需格式:

[
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
]

Phase 4 实现范围:
    - 处理 context.system_prompt
    - 处理 UserMessage 中的纯文本 content
    - 处理 AssistantMessage 中的 TextContent

暂时不处理:
    - ToolCall
    - ToolResultMessage
    - ImageContent
    - ThinkingContent

扩展方向:
    - Phase 5: 处理 streaming response
    - Phase 6: 处理真实 tool calling, 包括 ToolCall 和 ToolResultMessage
    - 后续多模态: 处理 ImageContent
    - 后续 reasoning: 处理 ThinkingContent
"""

def context_to_openai_messages(context: Context) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    if context.system_prompt:
        messages.append({"role": "system", "content": context.system_prompt})

    for message in context.messages:
        # Recall: UserMessage 的 content 由两种形态: str | 内容块列表(文本 or 图像)
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                content = message.content
            else:
                content = "\n".join(
                    block.text for block in message.content if isinstance(block, TextContent)
                )
            messages.append({"role": "user", "content": content})

        # Recall: AssistantMessage 的 content 为内容块列表(文本/Thinking/ToolCall)
        elif isinstance(message, AssistantMessage):
            content = "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )
            messages.append({"role": "assistant", "content": content})

    return messages

"""  4. 调用 Qwen chat completions  """
"""
这一步对应 packages/ai 中 provider 的真实请求部分。

当前 Phase 4 只做非流式文本调用:
    OpenAI-compatible messages
        -> Qwen chat completions API
        -> assistant 文本 content

暂时不处理:
    - stream=True 的流式返回
    - tools / tool_calls
    - provider response 到 AssistantMessage 的完整转换

本阶段会解析 provider response 中的 token usage, 但 cost 暂时保留为 0。
"""
from openai import OpenAI
from p1_types import Usage


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


def call_qwen_complete(api_key: str, messages: list[dict[str, str]]) -> tuple[str, Usage]:
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


"""  5. 解析 response 并构造 AssistantMessage  """
"""
Step 4 得到的是 provider 返回的 assistant 文本和 usage。

这里把它们包装回 Phase 1 定义的 AssistantMessage:
    assistant text
        -> TextContent
        -> AssistantMessage.content

    provider usage
        -> Usage
        -> AssistantMessage.usage

这一步对应 packages/ai 中 provider response 到统一 AssistantMessage 的转换。
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

"""  6. Context 更新  """
"""
将得到的 AssistantMessage append 到 context 的 messages 中
略
"""

if __name__ == "__main__":
    import json
    from dataclasses import asdict

    print("="*60)
    api_key = get_qwen_api_key()
    print("QWEN_API_KEY loaded")

    print("="*60)
    context = create_context()
    print(json.dumps({"Context": asdict(context)}, indent=2, ensure_ascii=False))

    print("="*60)
    openai_messages = context_to_openai_messages(context)
    print(json.dumps({"OpenAIMessages": openai_messages}, indent=2, ensure_ascii=False))

    print("="*60)
    assistant_text, usage = call_qwen_complete(api_key, openai_messages)
    print(json.dumps({"QwenAssistantText": assistant_text}, indent=2, ensure_ascii=False))
    print(json.dumps({"QwenUsage": asdict(usage)}, indent=2, ensure_ascii=False))
    
    print("="*60)
    assistant_message = create_assistant_message_from_text(assistant_text, usage)
    context.messages.append(assistant_message)
    print(json.dumps({"ContextAfterAssistant": asdict(context)}, indent=2, ensure_ascii=False))
    print("="*60)