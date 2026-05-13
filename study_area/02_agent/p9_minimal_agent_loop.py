"""  总览: Minimal Agent Loop / 最小 Agent 主循环  """
"""
目标: 在 P8 mini_pi_ai 的基础上, 对照 packages/agent/src/agent-loop.ts, 写一个更接近 agent 包结构的最小循环。

P8 已完成:
    - Context memory
    - Qwen streaming
    - ToolCall parsing
    - ToolResultMessage
    - run_agent_loop()

P9 重点:
    不重新实现 Qwen / tools / memory。
    复用 P8 模块, 但重新组织 agent 层概念。

核心问题:
    1. agent loop 比单次 LLM call 多了什么?
    2. agent state 如何表示?
    3. agent event 和 model stream event 有什么区别?
    4. agent 如何决定 continue / stop?
    5. max turns / error handling 如何保护循环?
"""

"""  1. 基础依赖 / 复用 P8 能力  """
"""
本阶段先复用 P8:
    p8_mini_pi_ai.types
    p8_mini_pi_ai.context
    p8_mini_pi_ai.qwen
    p8_mini_pi_ai.tools
    p8_mini_pi_ai.memory

注意:
    P9 的重点是 agent 层, 不是 provider adapter。

路径说明:
    P9 位于 study_area/02_agent。
    P8 已复制到 study_area/02_agent/p8_mini_pi_ai。
    因此可以直接 import 同级 package。
"""
import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from typing import Literal, TypedDict

from p8_mini_pi_ai.context import context_to_openai_messages, tools_to_openai_tools
from p8_mini_pi_ai.memory import load_context, save_context
from p8_mini_pi_ai.qwen import get_qwen_api_key, stream_qwen
from p8_mini_pi_ai.stream import AssistantMessageEvent
from p8_mini_pi_ai.tools import create_tools, execute_tool_call
from p8_mini_pi_ai.types import (
    AssistantMessage,
    Context,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


"""  2. AgentState / Agent 状态  """
"""
AgentState 用来描述一次 agent run 的运行状态。

可以包含:
    - context: 当前上下文
    - turn_index: 当前第几轮
    - max_turns: 最大循环次数
    - stopped: 是否停止
    - stop_reason: 为什么停止

对应 P8:
    run_agent_loop(api_key, context, max_turns=5)

对应源码关注:
    packages/agent/src/types.ts
    packages/agent/src/agent-loop.ts
"""


"""  3. AgentEvent / Agent 事件  """
"""
Model stream event 描述模型生成过程:
    text_delta
    toolcall_delta
    done

AgentEvent 描述 agent 行为过程:
    agent_start
    model_start
    model_done
    tool_start
    tool_done
    agent_done
    agent_error

区别:
    stream event 是模型层事件。
    agent event 是 agent 编排层事件。
"""


"""  4. create_initial_state  """
"""
创建一次 agent run 的初始状态。

输入:
    Context
    max_turns

输出:
    AgentState

注意:
    这里不负责创建 Context。
    Context 创建仍然可以由 main / memory 层负责。
"""


"""  5. append_user_message  """
"""
将用户输入追加到 Context.messages。

这一步表示:
    外部用户输入进入 agent state。

对应 P8:
    p8_mini_pi_ai.agent_loop.append_user_message
"""


"""  6. call_model_once  """
"""
执行一次模型调用。

流程:
    Context -> OpenAI messages
    tools -> OpenAI tools
    stream_qwen(...)
    consume stream events
    得到 AssistantMessage
    append 到 Context.messages

输出:
    AssistantMessage

注意:
    这里只表示“一次模型动作”。
    是否继续循环由后面的 decide_next_step 决定。
"""


"""  7. extract_tool_calls  """
"""
从 AssistantMessage.content 中提取 ToolCall。

如果存在 ToolCall:
    agent 需要执行工具, 然后继续下一轮模型调用。

如果不存在 ToolCall:
    agent 可以停止, 因为模型已经给出最终回答。
"""


"""  8. execute_tools  """
"""
执行模型请求的所有工具调用。

流程:
    ToolCall
        -> execute_tool_call
        -> ToolResultMessage
        -> append 到 Context.messages

这一步对应 agent 里的 environment observation。
"""


"""  9. decide_next_step  """
"""
根据当前状态决定下一步。

可能结果:
    continue: 有 ToolCall, 且未超过 max_turns
    stop: 没有 ToolCall
    error: 超过 max_turns 或执行失败

这是 agent loop 和普通模型调用最不同的地方。
"""


"""  10. run_agent  """
"""
主循环。

伪代码:
    state = create_initial_state(context, max_turns)
    yield agent_start

    while not state.stopped:
        yield model_start
        assistant_message = call_model_once(state)
        yield model_done

        tool_calls = extract_tool_calls(assistant_message)
        if not tool_calls:
            state.stopped = True
            state.stop_reason = "stop"
            break

        for tool_call in tool_calls:
            yield tool_start
            tool_result = execute_tool_call(tool_call)
            append tool_result
            yield tool_done

        state.turn_index += 1
        if state.turn_index >= state.max_turns:
            state.stopped = True
            state.stop_reason = "max_turns"

    yield agent_done

最终输出:
    AgentState / Context
"""


"""  11. main demo  """
"""
本文件先作为结构练习。
后续实现时可以:
    1. 读取 QWEN_API_KEY
    2. load_context() or create_context()
    3. append_user_message()
    4. run_agent()
    5. save_context()

运行方式建议:
    cd study_area/02_agent
    python p9_minimal_agent_loop.py
"""
