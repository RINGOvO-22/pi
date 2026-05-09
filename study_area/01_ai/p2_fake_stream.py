"""  总览: 流式事件类型  """
"""
性质: 从 Phase 1 的“静态类型”进入“动态生成过程”.

目标: 理解"AssistantMessage 不是一次性出现的, 而是通过 stream event 一步步构造出来的.
    注意, 不是学模型如何根据上下文生成内容。  

流程概述: 
    - 流的输出以 "事件" 为单位.
    - start 事件: 表示 assistant response 开始, 携带一个初始 partial AssistantMessage。(类型: list<内容块>).
    - 中间的事件: 
        - content 会随着模型流式输出(以事件为单位), 被逐渐填充内容. 
        - 一组连续同类型事件(例如, text 从 start 到 end), 对应的是在同一个 content 列表元素上的增量操作. content_index 表示当前事件对应 AssistantMessage.content 中的第几个内容块。
        - 所有的 event 都会用一个字段储存当前的 AssistantMessage. 多数在 "partial". 结尾 (done/error) 事件用 "message"/"error" 储存.
    - done 事件: 代表当前 AssistantMessage 实例生成完毕

对应源码概念:
    start
    text_start
    text_delta
    text_end
    toolcall_start
    toolcall_delta
    toolcall_end
    done
    error

重点看: 
   packages/ai/src/stream.ts
   packages/ai/src/utils/event-stream.ts

源码总结:
    stream.ts 负责路由到 api 对应的 provider 并返回事件流; 
    event-stream.ts 负责把 provider 推送的事件包装成可 async iterate, 可 result() 的流.
"""

"""  stream.ts  解读"""
"""
定位: 统一入口
作用: 根据 model.api 找到 provider，然后调用 provider 的 stream 函数. 注意: 这里的函数本身不负责生成模型输出, 只是路由, 根据 api 找到对应的 provider 实现并调用.

例如: 
    model.api = "openai-completions"                                
                 ↓                                                             
    调用 OpenAI-compatible provider 

内容: 定义了 stream() 函数以及 complete() 函数 (此外还有simple版本, 更统一/上层. 暂略)

函数:
    1. stream(): 返回事件流
    2. complete(): 内部会调用 stream(). 但是不会逐个消费事件, 而是等最终结果然后统一输出.

"""
from collections.abc import Iterator
from typing import Literal, TypedDict
from p1_types import (
    AssistantMessage,
    Context,
    StopReason,
    TextContent,
    ToolCall,
    Usage,
)

# AssistantMessageEvent 联合类型中的各个事件变体
class StartEvent(TypedDict):
    type: Literal["start"]
    partial: AssistantMessage

class TextStartEvent(TypedDict):
    type: Literal["text_start"]
    content_index: int
    partial: AssistantMessage

class TextDeltaEvent(TypedDict):
    type: Literal["text_delta"]
    content_index: int
    delta: str
    partial: AssistantMessage

class TextEndEvent(TypedDict):
    type: Literal["text_end"]
    content_index: int
    content: str
    partial: AssistantMessage

class ToolCallStartEvent(TypedDict):
    type: Literal["toolcall_start"]
    content_index: int
    partial: AssistantMessage

class ToolCallDeltaEvent(TypedDict):
    type: Literal["toolcall_delta"]
    content_index: int
    delta: str
    partial: AssistantMessage

class ToolCallEndEvent(TypedDict):
    type: Literal["toolcall_end"]
    content_index: int
    tool_call: ToolCall
    partial: AssistantMessage

class DoneEvent(TypedDict):
    type: Literal["done"]
    reason: StopReason
    message: AssistantMessage

class ErrorEvent(TypedDict):
    type: Literal["error"]
    reason: Literal["error", "aborted"]
    error: AssistantMessage

AssistantMessageEvent = (
    StartEvent
    | TextStartEvent
    | TextDeltaEvent
    | TextEndEvent
    | ToolCallStartEvent
    | ToolCallDeltaEvent
    | ToolCallEndEvent
    | DoneEvent
    | ErrorEvent
)

def fake_stream(context: Context) -> Iterator[AssistantMessageEvent]:
    """
    功能: 模拟如下场景:
        模型先输出一段文本：“我需要调用 get_time 工具。”
        然后请求调用 get_time 工具
        最后结束，返回完整 AssistantMessage

    注意:
        当前 fake provider 暂时不根据 context 生成内容。
        真实 provider 会根据 context.messages / context.tools / context.system_prompt 生成响应。
    """
    text = "我需要调用 get_time 工具。"

    tool_call = ToolCall(
        type="toolCall",
        id="call_1",
        name="get_time",
        arguments={"timezone": "Asia/Shanghai"},
    )

    final_message = AssistantMessage(
        role="assistant",
        content=[
            TextContent(type="text", text=text),
            tool_call,
        ],
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=0,
    ) # 示例. 最终 partial_message 中的值会变成该 final_message 的样子(主要是content字段).

    partial_message = AssistantMessage(
        role="assistant",
        content=[],
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=0,
    )

    # yield: 使当前函数成为一个 generator, 多次调用会依次返回一个对应的 yield 内容 (这里每次返回一个 AssistantMessageEvent)

    # 1. start
    # assistant response 开始了. 还没有生成任何内容块, 即 partial_message.content 为空列表.
    yield {
        "type": "start",
        "partial": partial_message,
    }

    # 2. text_start
    # 第一个 content block 开始了
    # partial_message.content 有了第一个内容块 (类型: textContent), 但文本内容为空. 后续也会直接修改这个 content[0]
    partial_message.content.append(TextContent(type="text", text=""))

    yield {
        "type": "text_start",
        "content_index": 0,
        "partial": partial_message,
    }

    # 3. 多次 text_delta
    # 每个 text_delta 表示模型又生成了一个文本增量
    text_so_far = ""
    for char in text:
        text_so_far += char
        partial_message.content[0] = TextContent(type="text", text=text_so_far)
        yield {
            "type": "text_delta",
            "content_index": 0,
            "delta": char,
            "partial": partial_message,
        }

    # 4. text_end
    # 表示第一个文本块生成完成. 至此, partial_message.content[0] 已经是完整的文本.
    yield {
        "type": "text_end",
        "content_index": 0,
        "content": text,
        "partial": partial_message,
    }

    # 5. toolcall_start
    # 表示第二个 content block 开始了
    # 这个内容块为 toolCall 类型.
    # partial_message 的 content 字段 (content block list) 新增一个内容块元素.
    # 此时工具名已经有了, 参数还是空的.
    partial_message.content.append(
        ToolCall(
            type="toolCall",
            id=tool_call.id,
            name=tool_call.name,
            arguments={},
        )
    )

    yield {
        "type": "toolcall_start",
        "content_index": 1,
        "partial": partial_message,
    }

    # 6. toolcall_delta
    # 表示模型正在流式生成工具参数 (此时可能还不完整)
    # 这一个事件模拟工具调用参数生成到一半
    partial_message.content[1] = ToolCall(
        type="toolCall",
        id=tool_call.id,
        name=tool_call.name,
        arguments={"timezone": "Asia"},
    )

    yield {
        "type": "toolcall_delta",
        "content_index": 1,
        "delta": '{"timezone": "Asia"}', # 完整参数: "{"timezone": "Asia/Shanghai"}"
        "partial": partial_message,
    }

    # 7. toolcall_end
    # 模拟工具调用参数生成完成 (直接给 content[1] 赋值了我们模拟的完整 toolCall 实例)
    partial_message.content[1] = tool_call

    yield {
        "type": "toolcall_end",
        "content_index": 1,
        "tool_call": tool_call,
        "partial": partial_message,
    }

    # 8. done
    # 表示本次 assistant message 生成结束
    # 且结束原因是 toolUse, 即模型请求工具调用, 而非普通的回答完成
    # message 中保存最终完整的 AssistantMessage
    yield {
        "type": "done",
        "reason": "toolUse",
        "message": final_message,
    }

"""  event-stream.ts 解读"""
"""
定位: 事件流容器

两个类型参数: 
    - T: 流里每次 yield 的事件类型
    - R: 最终 result() 返回的结果类型
    
参数解释: 对 assistant 来说: 
   - T = AssistantMessageEvent
   - R = AssistantMessage

容器内部:
    维护以下四个变量:
        1. queue: 时间已经来了, 但消费者还没取
        2. waiting: 消费者在等事件
        3. done: 流是否结束
        4. final_result_promis: 最终结果

    函数:
        1. push(event): provider 产生事件后 push 进 EventStream, 并做处理
        2. async iterator: 支持事件循环
        3. result(): 返回最终结果. e.g., 对于 assistant stream, 该函数的返回值就被作为 AssistantMessage


子类: AssistantMessageEventStream: 最终一定返回 AssistantMessage
"""
if __name__ == "__main__":
    import json
    from dataclasses import asdict
    # 下面这段模拟消费 EventStream:
    # - for event in fake_stream(context): 对应 for await (const event of stream)
    # - done.message 对应 stream.result()
    context = Context(messages=[])
    final_message = None

    for event in fake_stream(context):
        print(event["type"])
        if event["type"] == "done": # 取 DoneEvent 查看最终的 AssistantMessage
            final_message = event["message"]

    print(json.dumps({"final_message": asdict(final_message)}, indent=2, ensure_ascii=False))