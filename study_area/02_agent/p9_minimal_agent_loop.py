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

关键概念:
    agent_start -> agent_end 表示一次用户请求触发的完整 agent 活动。
    对用户来说, 它通常对应“发出一条 user message 到收到最终 assistant reply”的过程。
    但内部可能包含多次模型调用、工具调用和 tool result 回填。
    turn 表示其中一轮 assistant response 以及该轮触发的工具执行。
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
    context_memory.json: 位于 p8 中. 可直接删除来重置.
"""
import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Literal, TypedDict

from p8_mini_pi_ai_copy.context import context_to_openai_messages, tools_to_openai_tools
from p8_mini_pi_ai_copy.memory import load_context, save_context
from p8_mini_pi_ai_copy.qwen import get_qwen_api_key, stream_qwen
from p8_mini_pi_ai_copy.stream import AssistantMessageEvent
from p8_mini_pi_ai_copy.tools import create_tools, execute_tool_call
from p8_mini_pi_ai_copy.types import (
    AssistantMessage,
    Context,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


"""  2. AgentContext / AgentState  """
"""
源码中有两个相关概念:
    (1) AgentContext:
        一次 agent loop 的上下文快照。
        包含 systemPrompt / messages / tools。

    (2) AgentState:
        agent 当前可观察运行状态。
        除了上下文, 还包含 isStreaming / streamingMessage / pendingToolCalls / errorMessage 等运行时信息。

P9 简化:
    不单独定义 AgentContext。
    直接复用 P8 的 Context 作为 AgentContext。

可以理解为:
    AgentContext = Context
    AgentState = Context + runtime state

对应源码:
    packages/agent/src/types.ts
"""

@dataclass
class AgentState:
    context: Context
    turn_index: int
    max_turns: int
    stopped: bool = False
    stop_reason: str | None = None
    is_streaming: bool = False
    streaming_message: AssistantMessage | None = None
    pending_tool_calls: set[str] = field(default_factory=set)
    error_message: str | None = None


"""  3. AgentEvent / Agent 事件  """
"""
Model stream event 描述模型生成过程:
    text_delta
    toolcall_delta
    done

AgentEvent 描述 agent 行为过程。
它比 model stream event 更高一层, 用来给 UI / 日志 / hook 观察整个 agent run。

生命周期:
    agent_start: 一次 agent run 开始。
    agent_end: 一次 agent run 结束, 携带本次产生的 messages。

Turn 生命周期:
    turn_start: 一轮 assistant response 开始。
    turn_end: 一轮 assistant response 以及该轮工具执行结束。

Message 生命周期:
    message_start: 一条 message 开始。
    message_update: assistant streaming 中的增量更新, 内部携带 AssistantMessageEvent。
    message_end: 一条 message 完成。

Tool 生命周期:
    tool_execution_start: 工具开始执行。
    tool_execution_update: 工具执行中的 partial update, 用于长任务进度或中间结果。
    tool_execution_end: 工具执行完成, 携带最终结果和 is_error。

区别:
    stream event 是模型层事件。
    agent event 是 agent 编排层事件。
    message_update 是两者的连接点: AgentEvent 包住 AssistantMessageEvent。

P9 和源码:
    这里基本保留源码 AgentEvent 的核心结构。
    字段名使用 Python snake_case, 例如 tool_call_id / tool_results。

对应源码:
    packages/agent/src/types.ts AgentEvent
"""

AgentMessage = UserMessage | AssistantMessage | ToolResultMessage


class AgentStartEvent(TypedDict):
    type: Literal["agent_start"]


class AgentEndEvent(TypedDict):
    type: Literal["agent_end"]
    messages: list[AgentMessage]


class TurnStartEvent(TypedDict):
    type: Literal["turn_start"]


class TurnEndEvent(TypedDict):
    type: Literal["turn_end"]
    message: AgentMessage
    tool_results: list[ToolResultMessage]


class MessageStartEvent(TypedDict):
    type: Literal["message_start"]
    message: AgentMessage


class MessageUpdateEvent(TypedDict):
    type: Literal["message_update"]
    message: AgentMessage
    assistant_message_event: AssistantMessageEvent


class MessageEndEvent(TypedDict):
    type: Literal["message_end"]
    message: AgentMessage


class ToolExecutionStartEvent(TypedDict):
    type: Literal["tool_execution_start"]
    tool_call_id: str
    tool_name: str
    args: dict


class ToolExecutionUpdateEvent(TypedDict):
    type: Literal["tool_execution_update"]
    tool_call_id: str
    tool_name: str
    args: dict
    partial_result: object


class ToolExecutionEndEvent(TypedDict):
    type: Literal["tool_execution_end"]
    tool_call_id: str
    tool_name: str
    result: object
    is_error: bool


AgentEvent = (
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent
)


"""  4. create_initial_state  """
"""
创建一次 agent run 的初始状态。

输入:
    context: 已有 Context, 相当于源码里的 AgentContext。
    max_turns: 最大循环次数, 用来防止无限 tool loop。

输出:
    AgentState

作用:
    把静态 Context 包装成可运行状态。
    后续 loop 会持续更新 turn_index / stopped / stop_reason / is_streaming / pending_tool_calls。

不负责:
    - 创建 Context
    - 读取 memory
    - 追加 UserMessage
    - 调用模型
    - 执行工具
    - 保存 Context

对应关系:
    P8: run_agent_loop(api_key, context, max_turns=5)
    P9: state = create_initial_state(context, max_turns)

可以理解为:
    Context -> AgentState
"""

def create_initial_state(context: Context, max_turns: int = 5) -> AgentState:
    return AgentState(
        context=context,
        turn_index=0,
        max_turns=max_turns,
    )


"""  5. append_user_message  """
"""
将用户输入追加到 Context.messages。

这一步表示:
    外部用户输入进入 agent state。

P9:
    messages 位于 state.context.messages。
    返回 UserMessage, 方便后续 emit message_start / message_end。

对应 P8:
    p8_mini_pi_ai.agent_loop.append_user_message
"""

def now_ms() -> int:
    return int(time.time() * 1000)


def append_user_message(state: AgentState, content: str) -> UserMessage:
    message = UserMessage(
        role="user",
        content=content,
        timestamp=now_ms(),
    )
    state.context.messages.append(message)
    return message


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

对应源码:
    packages/agent/src/agent-loop.ts streamAssistantResponse(...)
"""

def consume_model_events(
    state: AgentState,
    events: Iterator[AssistantMessageEvent],
    char_delay: float = 0.0,
) -> AssistantMessage:
    final_message: AssistantMessage | None = None

    for event in events:
        if event["type"] in {"start", "text_start", "text_delta", "toolcall_start", "toolcall_delta", "toolcall_end"}:
            state.streaming_message = event["partial"]

        if event["type"] == "text_delta":
            if char_delay > 0:
                for char in event["delta"]:
                    print(char, end="", flush=True)
                    time.sleep(char_delay)
            else:
                print(event["delta"], end="", flush=True)

        elif event["type"] == "done":
            final_message = event["message"]

    print()

    if final_message is None:
        raise RuntimeError("Model stream ended without done event")

    return final_message


def call_model_once(
    api_key: str,
    state: AgentState,
    char_delay: float = 0.0,
) -> AssistantMessage:
    state.is_streaming = True
    state.streaming_message = None

    try:
        openai_messages = context_to_openai_messages(state.context)
        openai_tools = tools_to_openai_tools(state.context.tools)
        events = stream_qwen(api_key, openai_messages, openai_tools) # 是一个 iterator
        assistant_message = consume_model_events(state, events, char_delay=char_delay)
        state.context.messages.append(assistant_message)
        return assistant_message
    finally:
        state.is_streaming = False
        state.streaming_message = None


"""  7. extract_tool_calls  """
"""
从 AssistantMessage.content 中提取 ToolCall。

如果存在 ToolCall:
    agent 需要执行工具, 然后继续下一轮模型调用。

如果不存在 ToolCall:
    agent 可以停止, 因为模型已经给出最终回答。

对应源码:
    packages/agent/src/agent-loop.ts
    const toolCalls = message.content.filter((c) => c.type === "toolCall");
"""

def extract_tool_calls(message: AssistantMessage) -> list[ToolCall]:
    return [
        block
        for block in message.content
        if isinstance(block, ToolCall)
    ]


"""  8. execute_tools  """
"""
执行模型请求的所有工具调用。

流程:
    ToolCall
        -> execute_tool_call
        -> ToolResultMessage
        -> append 到 Context.messages

这一步对应 agent 里的 environment observation。

P9 简化:
    顺序执行所有工具。
    使用 state.pending_tool_calls 标记正在执行的 tool call id。

源码中 executeToolCalls(...) 还包含:
    - 参数校验
    - beforeToolCall / afterToolCall hook
    - sequential / parallel 执行模式
    - tool_execution_start / update / end events
    - terminate hint
"""

def execute_tools(state: AgentState, tool_calls: list[ToolCall]) -> list[ToolResultMessage]:
    tool_results: list[ToolResultMessage] = []

    for tool_call in tool_calls:
        state.pending_tool_calls.add(tool_call.id)
        try:
            tool_result = execute_tool_call(tool_call)
            tool_results.append(tool_result)
            state.context.messages.append(tool_result)
        finally:
            state.pending_tool_calls.discard(tool_call.id)

    return tool_results


"""  9. decide_next_step  """
"""
根据当前状态决定下一步。

可能结果:
    continue: 有 ToolCall, 且未超过 max_turns
    stop: 没有 ToolCall
    error: 超过 max_turns 或模型返回 error/aborted

这是 agent loop 和普通模型调用最不同的地方。

源码中该逻辑分散在 runLoop() 中:
    - stopReason error / aborted
    - toolCalls.length
    - executedToolBatch.terminate
    - shouldStopAfterTurn
    - steering / follow-up messages

P9 先只处理:
    - error / aborted
    - 没有 tool call
    - max_turns
    - 有 tool call 继续
"""

AgentDecision = Literal["continue", "stop", "error"]


def decide_next_step(
    state: AgentState,
    assistant_message: AssistantMessage,
    tool_calls: list[ToolCall],
) -> AgentDecision:
    if assistant_message.stop_reason in {"error", "aborted"}:
        state.stopped = True
        state.stop_reason = assistant_message.stop_reason
        state.error_message = assistant_message.error_message
        return "error"

    if not tool_calls:
        state.stopped = True
        state.stop_reason = "stop"
        return "stop"

    if state.turn_index + 1 >= state.max_turns:
        state.stopped = True
        state.stop_reason = "max_turns"
        state.error_message = f"Agent loop exceeded max_turns={state.max_turns}"
        return "error"

    return "continue"


"""  10. run_agent  """
"""
主循环。

流程说明:
    1. 先用 Context 创建 AgentState。
    2. 发出 agent_start, 表示本次 agent run 开始。
    3. 每一轮先发出 turn_start, 表示一个 assistant turn 开始。
    4. 调用模型生成 AssistantMessage, 并将其追加到 Context.messages。
    5. 发出 message_start / message_end, 表示 assistant message 已完成。
    6. 从 assistant message 中提取 ToolCall。
    7. 根据 ToolCall 和 stop_reason 决定下一步:
        - 没有 ToolCall: 结束。
        - error / aborted: 结束。
        - 达到 max_turns: 结束。
        - 有 ToolCall 且未超限: 执行工具。
    8. 执行工具时发出 tool_execution_start / tool_execution_end。
    9. 工具结果会追加到 Context.messages, 然后进入下一轮。
    10. 结束前发出 agent_end, 携带最终 messages。

注意:
    P9 的 run_agent 是 event generator。
    调用方通过遍历 AgentEvent 观察 agent 的运行过程。
"""

def run_agent(
    api_key: str,
    state: AgentState,
    char_delay: float = 0.0,
) -> Iterator[AgentEvent]:
    yield {"type": "agent_start"}

    while not state.stopped:
        yield {"type": "turn_start"}

        assistant_message = call_model_once(api_key, state, char_delay=char_delay)
        yield {"type": "message_start", "message": assistant_message}
        yield {"type": "message_end", "message": assistant_message}

        tool_calls = extract_tool_calls(assistant_message)
        decision = decide_next_step(state, assistant_message, tool_calls)

        tool_results: list[ToolResultMessage] = []
        if decision == "continue":
            for tool_call in tool_calls:
                yield {
                    "type": "tool_execution_start",
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "args": tool_call.arguments,
                }

                tool_result = execute_tools(state, [tool_call])[0]
                tool_results.append(tool_result)

                yield {
                    "type": "tool_execution_end",
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "result": tool_result,
                    "is_error": tool_result.is_error,
                }

            state.turn_index += 1

        yield {
            "type": "turn_end",
            "message": assistant_message,
            "tool_results": tool_results,
        }

        if decision != "continue":
            break

    yield {
        "type": "agent_end",
        "messages": state.context.messages,
    }


"""  11. main demo  """
"""
终端交互 demo。

流程:
    1. 读取 QWEN_API_KEY。
    2. load_context() or create_context()。
    3. 循环读取用户输入。
    4. 输入 q / quit / exit 时退出。
    5. 每次输入都会 append UserMessage。
    6. run_agent() 负责模型调用、工具调用和最终回复。
    7. 回复以打字机效果输出。
    8. 每轮结束后保存 Context。

运行方式:
    cd study_area/02_agent
    python p9_minimal_agent_loop.py
"""

def create_context() -> Context:
    return Context(
        system_prompt=(
            "我正在借当前项目学习 agent 应用开发。"
            "你是我的学习助手。"
            "如果需要了解项目结构或学习进度, 优先调用可用工具。"
            "回答要简洁明了, 不要使用特殊符号"
        ),
        messages=[],
        tools=create_tools(),
    )


if __name__ == "__main__":
    api_key = get_qwen_api_key()
    context = load_context() or create_context()

    while True:
        user_input = input("user: ").strip()
        if user_input.lower() in {"q", "quit", "exit"}:
            break
        if not user_input:
            continue

        state = create_initial_state(context)
        append_user_message(state, user_input)

        print("assistant: ", end="", flush=True)
        for event in run_agent(api_key, state, char_delay=0.01):
            if event["type"] == "agent_end":
                state.context.messages = event["messages"]

        context = state.context
        save_context(context)
