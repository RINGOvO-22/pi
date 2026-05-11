"""  总览  """
"""
主题: 手写如下流程:
    assistant toolCall → 本地执行工具 → 追加 toolResult → 再次调用模型

流程解析:
    1. 初始 context
    2. context 输入模型, 得到 assistant message, 其中的 content 列表中存在 ToolCall 内容块. 将 message append 到 context.messages 中.
    3. 提取所有 ToolCall 内容块, 执行对应工具, 获得对应的 ToolResultMessage, append 到context.messages 中.
    4. 用更新的 context 再次输入模型, 得到 assistant message.

模拟的逻辑:
    每一次 AssistantMessage 的生成, 真实场景是 model + context + options 输入 provider, 得到 AssistantMessage

扩展项: 
    - 工具参数校验强化
    - 校验失败/执行失败如何转成 ToolResultMessage

    源码参考: validation.ts, validation.test.ts
"""

from dataclasses import asdict
import json
from pathlib import Path
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


def list_project_tree(root: str = ".", max_depth: int = 3) -> str:
    """
    本地工具: 返回该脚本往上 2 级路径下的目录 tree。
    """
    base_dir = Path(__file__).resolve().parents[1]
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


def fake_model_first_turn(context: Context) -> AssistantMessage:
    """
    第一次模型响应: 请求调用 list_project_tree。
    返回的 message 中, content 会包含两个内容块: TextContent + ToolCall
    """
    tool_call = ToolCall(
        type="toolCall",
        id="call_1",
        name="list_project_tree",
        arguments={"root": ".", "max_depth": 3},
    )

    return AssistantMessage(
        role="assistant",
        content=[
            TextContent(type="text", text="我需要先读取当前项目结构。"),
            tool_call,
        ],
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=0,
    )


def execute_tool_call(tool_call: ToolCall) -> ToolResultMessage:
    """
    执行模型请求的工具调用。
    """
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

    return ToolResultMessage(
        role="toolResult",
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=[TextContent(type="text", text=result)],
        is_error=is_error,
        timestamp=0,
    )


def fake_model_second_turn(context: Context) -> AssistantMessage:
    """
    第二次模型响应: 模拟真实模型基于包含 ToolResultMessage 的 context 生成最终回答
    """
    return AssistantMessage(
        role="assistant",
        content=[
            TextContent(
                type="text",
                text="根据项目结构, 你当前已经完成 Phase 1, 正在进入 Phase 3 的 tool loop 实践。",
            )
        ],
        usage=Usage(),
        stop_reason="stop",
        timestamp=0,
    )


if __name__ == "__main__":
    context = Context(
        messages=[
            UserMessage(
                role="user",
                content="请根据当前项目文件结构, 判断我在 agent 应用开发学习计划中进展到哪里了。",
                timestamp=0,
            )
        ],
        tools=[
            Tool(
                name="list_project_tree",
                description="List current project file tree.",
                parameters={
                    "type": "object",
                    "properties": {
                        "root": {"type": "string"},
                        "max_depth": {"type": "number"},
                    },
                },
            )
        ],
    )

    first_assistant_message = fake_model_first_turn(context)
    context.messages.append(first_assistant_message)

    tool_calls = [block for block in first_assistant_message.content if isinstance(block, ToolCall)] # 提取 message 的 content 列表中, 属于 ToolCall 的那些内容块
    for tool_call in tool_calls:
        tool_result = execute_tool_call(tool_call) # 返回一个 ToolResultMessage
        context.messages.append(tool_result)

    second_assistant_message = fake_model_second_turn(context)
    context.messages.append(second_assistant_message)

    print("=" * 60, "\n1 ContextAfterToolLoop / 工具循环后的上下文")
    print(json.dumps(asdict(context), indent=2, ensure_ascii=False))
    print("=" * 60)
