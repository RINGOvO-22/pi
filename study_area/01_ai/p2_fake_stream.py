"""  总览  """
"""
性质: 从 Phase 1 的“静态类型”进入“动态生成过程”.

目标: 理解"AssistantMessage 不是一次性出现的, 而是通过 stream event 一步步构造出来的.

概述: 
    stream.ts 负责路由到 api 对应的 provider 并返回事件流; 
    event-stream.ts 负责把 provider 推送的事件包装成可 async iterate, 可 result() 的流.

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
from p1_types import (
    AssistantMessage,
    Context,
    TextContent,
    ToolCall,
    Usage,
)

def fake_stream(context: Context):
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
    )

    yield {"type": "start", "partial": AssistantMessage(
        role="assistant",
        content=[],
        usage=Usage(),
        stop_reason="toolUse",
        timestamp=0,
    )}

    yield {"type": "text_start"}
    for char in text:
        yield {"type": "text_delta", "delta": char}
    yield {"type": "text_end", "text": text}

    yield {"type": "toolcall_start"}
    yield {"type": "toolcall_delta", "partial_arguments": {"timezone": "Asia"}}
    yield {"type": "toolcall_end", "tool_call": tool_call}

    yield {"type": "done", "message": final_message}

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
        3. result(): 返回最终结果. e.g., 对于 assistant stream, 该函数的返回值就被最为 AssistantMessage


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
        if event["type"] == "done":
            final_message = event["message"]

    print(json.dumps({"Context": asdict(final_message)}, indent=2, ensure_ascii=False))