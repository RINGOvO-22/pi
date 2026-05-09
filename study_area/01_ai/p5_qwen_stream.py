"""  总览: Qwen 流式调用  """
"""
目标: 在 P4 非流式调用的基础上, 实现 Qwen streaming response。

P4 非流式调用:
    response = client.chat.completions.create(...)
    text = response.choices[0].message.content

P5 流式调用:
    response = client.chat.completions.create(..., stream=True)

    for chunk in response:
        ...

核心变化:
    - P4 等完整 response 返回后, 一次性构造 AssistantMessage。
    - P5 每收到一个 chunk, 就转换成一个 stream event。
    - P5 需要维护 partial_message, 最后再得到 final AssistantMessage。

本阶段先只处理文本流:
    start
    text_start
    text_delta
    text_end
    done

暂时不处理:
    - toolcall_delta / toolcall_end
    - thinking
    - error 的完整映射
"""

"""  1. 准备 api key (复用 p4 内容)  """
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

"""  2. 构造 Context (复用 p4 内容)  """
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

"""  3. 转换 Context 为 API 所需格式 (复用 p4 内容)  """
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

"""  4. 调用 Qwen chat streaming  """
"""
这一步对应 packages/ai 中 provider 的真实请求部分。

当前 Phase 5 处理 stream=True:
    OpenAI-compatible messages
        -> Qwen chat completions streaming API
        -> chunks
        -> stream events

本阶段先只处理文本流:
    start
    text_start
    text_delta
    text_end
    done

暂时不处理:
    - tools / tool_calls
    - thinking
    - error 的完整映射
    - streaming usage 的完整映射
"""
from collections.abc import Iterator

from openai import OpenAI
from p1_types import Usage


def call_qwen_stream(api_key: str, messages: list[dict[str, str]]) -> Iterator[dict]:
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

    # 1. 输出 start 事件.
    # partial 为初始 message, 内容块列表为空.
    yield {
        "type": "start",
        "partial": partial_message,
    }

    # 2. 调用 Qwen 流式 API
    # 此时 response 是一个可迭代对象, 后面可以逐块读取模型输出
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        stream=True,
    )

    text_so_far = ""
    text_started = False # 表示已经开始输出文本了(输出过)

    for chunk in response:
        # 3. 遍历 chunk, 取文本增量
        # delta 是这一次新生成的文本片段
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        
        # 4. 第一次拿到文本时, 发 text_start
        if not text_started:
            partial_message.content.append(TextContent(type="text", text=""))
            text_started = True
            yield {
                "type": "text_start",
                "content_index": 0,
                "partial": partial_message,
            }

        text_so_far += delta
        partial_message.content[0] = TextContent(type="text", text=text_so_far)

        yield {
            "type": "text_delta",
            "content_index": 0,
            "delta": delta,
            "partial": partial_message,
        }

    if text_started:
        yield {
            "type": "text_end",
            "content_index": 0,
            "content": text_so_far,
            "partial": partial_message,
        }

    final_message = AssistantMessage(
        role="assistant",
        content=[TextContent(type="text", text=text_so_far)],
        usage=Usage(),
        stop_reason="stop",
        timestamp=now_ms(),
        api="openai-completions",
        provider="qwen",
        model="qwen-plus",
    )

    yield {
        "type": "done",
        "reason": "stop",
        "message": final_message,
    }


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

    api_key = get_qwen_api_key()
    print("QWEN_API_KEY loaded")

    context = create_context()
    print(json.dumps({"Context": asdict(context)}, indent=2, ensure_ascii=False))

    openai_messages = context_to_openai_messages(context)
    print(json.dumps({"OpenAIMessages": openai_messages}, indent=2, ensure_ascii=False))

    assistant_text, usage = call_qwen_complete(api_key, openai_messages)
    print(json.dumps({"QwenAssistantText": assistant_text}, indent=2, ensure_ascii=False))
    print(json.dumps({"QwenUsage": asdict(usage)}, indent=2, ensure_ascii=False))
    
    assistant_message = create_assistant_message_from_text(assistant_text, usage)
    context.messages.append(assistant_message)
    print(json.dumps({"ContextAfterAssistant": asdict(context)}, indent=2, ensure_ascii=False))
