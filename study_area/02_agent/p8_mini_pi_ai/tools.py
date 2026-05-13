"""  总览: 本地工具定义和执行  """
"""
目标: 把模型产生的 ToolCall 转成真实 Python 函数调用, 再包装成 ToolResultMessage。

三个主函数:
    create_tools(): 返回 agent 可用工具列表。
    list_project_tree(root, max_depth): 读取项目目录结构并返回字符串。
    execute_tool_call(tool_call): 执行 ToolCall, 返回 ToolResultMessage。

来源:
    迁移 P6 的 list_project_tree 工具逻辑。
"""

"""  1. 工具定义  """
"""
Tool 定义只是告诉模型有哪些能力。
真正执行发生在 execute_tool_call()。
"""
import time
from pathlib import Path

from .types import TextContent, Tool, ToolCall, ToolResultMessage


def now_ms() -> int:
    return int(time.time() * 1000)


def create_tools() -> list[Tool]:
    return [
        Tool(
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
                        "description": "目录深度。默认使用 3, 最大 5。",
                        "minimum": 0,
                        "maximum": 5,
                    },
                },
                "required": [],
            },
        )
    ]


"""  2. list_project_tree  """
"""
本地工具: 返回项目根目录下的目录 tree。

当前脚本路径:
    study_area/01_ai/p8_mini_pi_ai/tools.py

项目根目录:
    Path(__file__).resolve().parents[3]
"""

def list_project_tree(root: str = ".", max_depth: int = 3) -> str:
    base_dir = Path(__file__).resolve().parents[3]
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


"""  3. execute_tool_call  """
"""
执行模型请求的工具调用。

当前只支持:
    list_project_tree

执行失败时返回 is_error=True 的 ToolResultMessage。
"""

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
