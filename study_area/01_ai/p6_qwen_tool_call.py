"""  总览: Qwen 真实 Tool Calling  """
"""
目标: 在 P4/P5 真实 Qwen 调用的基础上, 实现真实 tool calling。

核心流程:
    1. 构造 Context 和 Tool 定义
    2. 将 Context + Tool 转成 OpenAI-compatible payload
    3. 第一次调用 Qwen, 让模型产生 tool_call
    4. 解析 Qwen 返回的 tool_call 为 ToolCall
    5. 执行本地工具 list_project_tree
    6. 将工具结果转成 ToolResultMessage, 并追加回 Context
    7. 将 ToolResultMessage 转成 OpenAI-compatible tool message
    8. 第二次调用 Qwen, 得到最终 AssistantMessage

本阶段工具:
    list_project_tree(root?: string, max_depth?: number)

任务场景:
    用户让模型根据当前项目文件结构判断学习进度。
    模型应调用 list_project_tree 获取项目 tree, 再基于 tool result 给出判断。
"""

"""  1. 准备 api key / 基础依赖  """
"""
复用 P4 的 .env 读取方式。
"""
import os
from pathlib import Path

from dotenv import load_dotenv


def get_qwen_api_key() -> str:
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)

    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError(f"Missing QWEN_API_KEY in {env_path}")

    return api_key

"""  2. 构造 Context 和 Tool 定义  """
"""
Context 包含:
    - system_prompt
    - UserMessage
    - tools=[list_project_tree]

Tool 定义需要同时存在两份表示:
    1. p1_types.Tool: 作为我们自己的统一抽象
    2. OpenAI-compatible tools payload: 发送给 Qwen API

对应源码:
    packages/ai/src/types.ts

阅读重点:
    - Tool.parameters 如何描述工具 schema
    - Context.tools 如何挂载工具定义

补充:
    parameters 是 JSON Schema 风格的工具参数 schema。
    它用于告诉模型工具接受哪些参数、参数类型、必填项和约束。
    例如 max_depth 的 type=integer, minimum=1, maximum=5。
    但 schema 只是约束说明, 模型仍可能生成错误参数, 所以执行工具前仍需要校验 ToolCall.arguments。
    
    文档参考:
        1. https://developers.openai.com/api/docs/guides/function-calling
        2. https://help.aliyun.com/zh/model-studio/qwen-function-calling
        3. https://json-schema.org/understanding-json-schema/reference/object
"""
from p1_types import AssistantMessage, Context, TextContent, Usage, UserMessage, Tool
import time

def now_ms() -> int:
    return int(time.time() * 1000)

def create_tool() -> Tool:
    return Tool(
        name="list_project_tree",
        description=(
            "列出当前学习项目的文件目录结构。"
            "用于检查用户的学习文件, 并推断当前学习进度。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": "相对于学习项目根目录的路径。默认使用 '.'。",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "从当前脚本所在目录开始向上回退的层数, 然后列出该目录下的文件树。默认使用 3。",
                    "minimum": 0,
                    "maximum": 5,
                },
            },
            "required": [],
        },
    )

def create_context() -> Context:
    return Context(
        messages=[
            UserMessage(
                role="user",
                content=(
                    "请读取当前项目目录, 根据 file tree 推断我当前的学习进度, "
                    "并给出后续内容的推断以及建议. 300字以内."
                ),
                timestamp=now_ms()
            )
        ],
        system_prompt="我正在借该项目学习agent开发, 你的身份是我的学习助手",
        tools=[
            create_tool()
        ]
    )

"""  3. Context / tools 转 OpenAI-compatible payload  """
"""
这是 P4 context_to_openai_messages 的扩展版。

需要转换:
    Context.messages -> messages (新增对 AssistantMessage 中的 ToolCall 以及 ToolResultMessage 的处理)

    Context.tools -> tools (tool list)

对应源码:
    packages/ai/src/providers/openai-completions.ts

阅读重点:
    - Tool 如何转成 OpenAI-compatible tools payload
    - ToolResultMessage 如何转成 provider 的 tool message
"""
from p1_types import ToolCall, ToolResultMessage
import json

def context_to_openai_messages(context: Context) -> list[dict[str, object]]:
    """
    和 p5 相比需要变动的:
        1. 返回值类型约束放宽
        2. assistant message 新增 tool_calls 字段
        3. 新增 role 为 tool 的 message (从 ToolResultMessage 转换)
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

            # 新增: assistant message 中可能包含 ToolCall 内容块
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
        # 可以先不看, 到 section 7 的时候在回来看.
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

def tools_to_openai_tools(tools: list[Tool]) -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        }
        for tool in tools
    ]

"""  4. 第一次调用 Qwen: 获取 tool_call  """
"""
复用 P4 的 Qwen chat completions 函数 (暂时先做非流式 tool calling).
区别:  
    P4 只传 messages。
    P6 额外传 tools, 并用 tool_choice="auto" 让模型自行决定是否调用工具。

预期结果:
    返回 Qwen/OpenAI-compatible 原始 response。
    response.choices[0].message 中可能包含 tool_calls。

对应源码:
    packages/ai/src/providers/openai-completions.ts
    packages/ai/test/openai-completions-tool-choice.test.ts

阅读重点:
    - tools 参数如何传给 provider
    - provider 如何返回 tool_calls

和 P4 普通 complete 的差异:
    P4 只传 messages。
    P6 额外传 tools, 并用 tool_choice="auto" 让模型自行决定是否调用工具。
"""
from openai import OpenAI

def call_qwen_for_tool_call(
    api_key: str,
    messages: list[dict[str, object]],
    tools: list[dict[str, object]],
):
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    return client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

"""  5. 解析 provider tool_call 为 ToolCall  """
"""
把 Qwen/OpenAI-compatible 返回的 tool_call 转成 p1_types.ToolCall。

关键字段映射:
    provider tool_call.id -> ToolCall.id
    provider tool_call.function.name -> ToolCall.name
    provider tool_call.function.arguments(JSON string) -> ToolCall.arguments(dict)

对应源码:
    packages/ai/src/providers/openai-completions.ts

阅读重点:
    - provider tool_call 如何规范化成统一 ToolCall
"""
def parse_provider_tool_call(provider_tool_call) -> ToolCall:
    try:
        # 根据 qwen (OpenAI compatible) 返回的 tool call 格式, 取出 arguments
        arguments = json.loads(provider_tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}
    
    return ToolCall(
        type="toolCall",
        id=provider_tool_call.id,
        name=provider_tool_call.function.name,
        arguments=arguments,
    )

def parse_provider_tool_call_list(provider_tool_call_list) -> list[ToolCall]:
    if not provider_tool_call_list:
        return []
    
    return [
        parse_provider_tool_call(provider_tool_call)
        for provider_tool_call in provider_tool_call_list
    ]


def create_assistant_message_from_tool_calls(tool_calls: list[ToolCall]) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=tool_calls,
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=now_ms(),
        api="openai-completions",
        provider="qwen",
        model="qwen-plus",
    )



"""  6. 执行本地工具 list_project_tree  """
"""
复用 P3 的 list_project_tree 思路。

注意:
    - 校验 root / max_depth
    - 限制读取范围和深度
    - 工具失败时返回 is_error=True 的 ToolResultMessage

对应源码:
    packages/ai/src/utils/validation.ts
    packages/ai/test/validation.test.ts

阅读重点:
    - 参数校验失败时如何返回 error tool result
    - validateToolCall / validateToolArguments 的职责
"""

def list_project_tree(root: str = ".", max_depth: int = 3) -> str:
    """
    本地工具: 返回项目根目录下的目录 tree。

    当前脚本路径:
        study_area/01_ai/p6_qwen_tool_call.py

    项目根目录:
        Path(__file__).resolve().parents[2]
    """
    base_dir = Path(__file__).resolve().parents[2]
    target = (base_dir / root).resolve()
    max_depth = max(0, min(max_depth, 5))
    ignored_names = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}

    if not target.exists():
        return f"Path not found: {target}"
    if not target.is_dir():
        return f"Not a directory: {target}"

    lines = [target.name]

    def walk(path: Path, depth: int, prefix: str = "") -> None:
        if depth >= max_depth:
            return

        children = sorted(
            [child for child in path.iterdir() if child.name not in ignored_names],
            key=lambda child: (not child.is_dir(), child.name.lower()),
        )

        for index, child in enumerate(children):
            is_last = index == len(children) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{child.name}")

            if child.is_dir():
                extension = "    " if is_last else "│   "
                walk(child, depth + 1, prefix + extension)

    walk(target, 0)
    return "\n".join(lines)


def execute_tool_call(tool_call: ToolCall) -> ToolResultMessage:
    if tool_call.name != "list_project_tree":
        result = f"Unknown tool: {tool_call.name}"
        is_error = True
    else:
        try:
            root = str(tool_call.arguments.get("root", "."))
            max_depth = int(tool_call.arguments.get("max_depth", 3))
            result = list_project_tree(root=root, max_depth=max_depth)
            is_error = False
        except (TypeError, ValueError) as error:
            result = f"Invalid tool arguments: {error}"
            is_error = True
        except Exception as error:
            result = f"Tool execution failed: {error}"
            is_error = True

    return ToolResultMessage(
        role="toolResult",
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=[TextContent(type="text", text=result)],
        is_error=is_error,
        timestamp=now_ms(),
    )

"""  7. ToolResultMessage 回填到 Context 和 provider messages  """
"""
内部结构:
    ToolResultMessage 追加到 context.messages

Provider payload:
    转成 OpenAI-compatible tool message:
        {"role": "tool", "tool_call_id": ..., "content": ...}

注意: 为了让 provider 接受 tool result，通常必须要让 assistant message 里之前的 toolcall id 和 tool result message 里的 id 匹配.

对应源码:
    packages/ai/src/types.ts
    packages/ai/src/providers/openai-completions.ts
    packages/ai/test/tool-call-without-result.test.ts

阅读重点:
    - ToolResultMessage 如何回填给模型
    - tool call 没有对应 tool result 时 provider 会如何处理
"""

# 1. ToolResultMessage 回填到 context.messages: 在 Main 中实现即可.

# 2. 转换 provider messages: section 3 中定义的 context_to_openai_messages 函数中已支持.

"""  8. 第二次调用 Qwen: 得到最终 AssistantMessage  """
"""
带着 tool result 再次请求 Qwen。

预期结果:
    模型基于项目 tree 判断当前学习进度, 并给出下一步建议。
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

"""  9. main: 串起完整 tool loop  """
"""
最终链路:
    UserMessage
        -> Qwen AssistantMessage(ToolCall)
        -> Python ToolResultMessage
        -> Qwen AssistantMessage(TextContent)
        -> ContextAfterToolLoop

当前先验证 Step 1-4:
    - 读取 API key
    - 构造 Context
    - 转换 OpenAI-compatible messages
    - 转换 OpenAI-compatible tools
    - 第一次调用 Qwen, 查看原始 response 中的 tool_calls
"""

if __name__ == "__main__":
    import json
    from dataclasses import asdict

    print("=" * 60, "\n1 API Key / 密钥")
    api_key = get_qwen_api_key()
    print("QWEN_API_KEY loaded")

    print("=" * 60, "\n2 Context / 上下文")
    context = create_context()
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))

    print("=" * 60, "\n3.1 OpenAI Messages / API 消息格式")
    openai_messages = context_to_openai_messages(context)
    print(json.dumps(openai_messages, indent=2, ensure_ascii=False))

    print("=" * 60, "\n3.2 OpenAI Tools / API 工具定义")
    openai_tools = tools_to_openai_tools(context.tools)
    print(json.dumps(openai_tools, indent=2, ensure_ascii=False))

    print("=" * 60, "\n4.1 Qwen Raw Assistant Message / Qwen 原始助手消息")
    response = call_qwen_for_tool_call(api_key, openai_messages, openai_tools)
    message = response.choices[0].message
    print(message)

    print("=" * 60, "\n4.2 Qwen Tool Calls / Qwen 工具调用")
    print(message.tool_calls)

    print("=" * 60, "\n5.1 Parsed ToolCalls / 解析后的工具调用")
    tool_calls = parse_provider_tool_call_list(message.tool_calls)
    print(json.dumps([asdict(tool_call) for tool_call in tool_calls], indent=2, ensure_ascii=False))

    print("=" * 60, "\n5.2 AssistantMessage With ToolCalls / 包含工具调用的助手消息")
    assistant_tool_call_message = create_assistant_message_from_tool_calls(tool_calls)
    context.messages.append(assistant_tool_call_message)
    print(json.dumps(asdict(assistant_tool_call_message), indent=2, ensure_ascii=False))

    print("=" * 60, "\n6 Tool Results / 工具执行结果")
    tool_results = [execute_tool_call(tool_call) for tool_call in tool_calls]
    print(json.dumps([asdict(tool_result) for tool_result in tool_results], indent=2, ensure_ascii=False))

    for tool_result in tool_results:
        context.messages.append(tool_result)

    print("=" * 60, "\n7.1 ContextAfterToolResults / 工具结果后的上下文")
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))

    print("=" * 60, "\n7.2 OpenAIMessagesAfterToolResults / 工具结果后的 API 消息格式")
    openai_messages_after_tools = context_to_openai_messages(context)
    print(json.dumps(openai_messages_after_tools, indent=2, ensure_ascii=False))

    print("=" * 60, "\n8.1 Qwen Final Raw Assistant Message / Qwen 最终原始助手消息")
    final_response = call_qwen_for_tool_call(api_key, openai_messages_after_tools, openai_tools)
    final_raw_message = final_response.choices[0].message
    print(final_raw_message)

    if final_raw_message.tool_calls:
        print("Model requested more tool calls; current P6 stops here.")
    else:
        print("=" * 60, "\n8.2 Final AssistantMessage / 最终助手消息")
        final_text = final_raw_message.content or ""
        final_usage = usage_from_qwen_response(final_response)
        final_assistant_message = create_assistant_message_from_text(final_text, final_usage)
        context.messages.append(final_assistant_message)
        print(json.dumps(asdict(final_assistant_message), indent=2, ensure_ascii=False))

        print("=" * 60, "\n8.3 ContextAfterToolLoop / 工具循环后的上下文")
        print(json.dumps(asdict(context), indent=2, ensure_ascii=False))

    print("=" * 60)