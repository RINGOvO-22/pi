"""  总览: mini_pi_ai 命令入口  """
"""
目标: 串起 P8 的完整最小 agent。

最终链路:
    get api key
    load/create Context
    append UserMessage
    run agent loop
    save Context
    print Context

运行方式:
    cd study_area/01_ai
    python -m p8_mini_pi_ai.main
"""

"""  1. 基础依赖  """
import json
from dataclasses import asdict
from pathlib import Path

from .agent_loop import append_user_message, run_agent_loop
from .memory import MEMORY_PATH, load_context, save_context
from .qwen import get_qwen_api_key
from .tools import create_tools
from .types import AssistantMessage, Context, TextContent

LAST_RESPONSE_PATH = Path(__file__).with_name("last_response.md")


"""  2. create_context  """
"""
如果没有记忆文件, 创建初始 Context。

P8 的 Context 包含:
    - system_prompt
    - messages=[]
    - tools=create_tools()
"""

def create_context() -> Context:
    return Context(
        system_prompt=(
            "我正在借当前项目学习 agent 应用开发。"
            "你是我的学习助手。"
            "如果需要了解项目结构或学习进度, 优先调用可用工具。"
            "回答要简洁明了, 不要说太多扩展内容, 不要用特殊符号"
        ),
        messages=[],
        tools=create_tools(),
    )


"""  3. last_response.md  """
"""
保存最近一次 assistant 的文本回复。

用途:
    context_memory.json 保存完整结构化上下文。
    last_response.md 只保存最后一条模型文本, 方便直接阅读。
"""

def get_last_assistant_text(context: Context) -> str:
    for message in reversed(context.messages):
        if isinstance(message, AssistantMessage):
            return "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )

    return ""


def save_last_response(context: Context, path: Path = LAST_RESPONSE_PATH) -> None:
    path.write_text(get_last_assistant_text(context), encoding="utf-8")


"""  4. main  """
"""
职责:
    1. 读取 API key
    2. 加载或创建 Context
    3. 追加用户消息
    4. 运行 agent loop
    5. 保存 Context
    6. 保存 last_response.md
"""

if __name__ == "__main__":
    one_turn = False

    api_key = get_qwen_api_key()
    loaded_context = load_context()
    context = loaded_context or create_context()

    if one_turn:
        print("=" * 60, "\n1 API Key / 密钥")
        print("QWEN_API_KEY loaded")

        print("=" * 60, "\n2.1 Load Context / 读取上下文记忆")
        if loaded_context is None:
            print(f"No memory file found: {MEMORY_PATH}")
        else:
            print(json.dumps(asdict(loaded_context), indent=2, ensure_ascii=False))

        print("=" * 60, "\n2.2 Context / 当前上下文")
        print(json.dumps(asdict(context), indent=2, ensure_ascii=False))
        print("=" * 60, "\n3 Append UserMessage / 追加用户消息")
        append_user_message(
            context,
            "请读取当前项目结构, 总结我在 mini_pi_ai 里已经完成了哪些模块, 并建议下一步。",
        )
        print(json.dumps(asdict(context.messages[-1]), indent=2, ensure_ascii=False))

        print("=" * 60, "\n4 Run Agent Loop / 运行 Agent 主循环")
        context = run_agent_loop(api_key, context)

        print("=" * 60, "\n5.1 Save Context / 保存上下文记忆")
        save_context(context)
        print(f"Saved to: {MEMORY_PATH}")

        print("=" * 60, "\n5.2 Save LastResponse / 保存最近回复")
        save_last_response(context)
        print(f"Saved to: {LAST_RESPONSE_PATH}")

        print("=" * 60, "\n6 ContextAfterAgentLoop / Agent 循环后的上下文")
        print(json.dumps(asdict(context), indent=2, ensure_ascii=False))
        print("=" * 60)
    else:
        while True:
            user_input = input("user: ").strip()
            if user_input.lower() in {"exit", "quit", "q"}:
                break
            if not user_input:
                continue

            append_user_message(context, user_input)
            print("assistant: ", end="", flush=True)
            context = run_agent_loop(api_key, context, verbose=False)
            save_context(context)
            save_last_response(context)
