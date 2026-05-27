# 概览
## 整体功能

1. 模型发现
2. provider 配置
3. 统一流式调用
4. tool calling
5. token / cost 统计
6. context 持久化
7. 跨 provider 切换
8. OAuth / API Key 管理

## 核心概念

### Model

具体模型.

例如:
 ```ts                                                                               
   const model = getModel("openai", "gpt-4o-mini");                                  
 ```   

信息中包含:
- provider                                                                                 
- api 类型                                                                                 
- context window                                                                           
- 是否支持 image                                                                           
- 是否支持 reasoning                                                                       
- cost                                                                                     
- max tokens

### Context

一次模型调用所需的上下文.

 ```ts                                                                               
   const context: Context = {                                                        
     systemPrompt: "You are a helpful assistant.",                                   
     messages: [                                                                     
       { role: "user", content: "What time is it?" }                                 
     ],                                                                              
     tools                                                                           
   };                                                                                
 ```   

一般包含:

- systemPrompt                                                                             
- messages                                                                                 
- tools 

### Message

模型可理解的消息.

主要有:
- user
- assistant
- toolResult

这是 agent 章节中, agent loop 的基础.

### Tool

工具定义. (这里使用 TypeBox schema).

```ts                                                                               
const tools: Tool[] = [{                                                          
    name: "get_time",                                                               
    description: "Get the current time",                                            
    parameters: Type.Object({                                                       
    timezone: Type.Optional(Type.String())                                        
    })                                                                              
}];                                                                               
```

至少包括:
- name
- description
- parameters

(这里只是定义, 不负责真正执行)

### ToolCall

当模型想使用工具时，会在 assistant message 里产生 toolCall 内容块。

例如:
```text                                                                             
assistant message                                                                 
    content:                                                                        
    - text                                                                        
    - toolCall                                                                    
```

应用层需要识别它, 然后执行对应工具.

### ToolResult

工具执行完成后，需要把结果追加回 context：

```ts                                                                               
context.messages.push({                                                           
    role: "toolResult",                                                             
    toolCallId: call.id,                                                            
    toolName: call.name,                                                            
    content: [{ type: "text", text: result }],                                      
    isError: false,                                                                 
    timestamp: Date.now()                                                           
});                                                                               
``` 

然后再次调用模型，让模型基于工具结果继续回答。

## 模型调用方式

### 1. 流式调用

```ts                                                                               
    const s = stream(model, context);                                                 
                                                                                        
    for await (const event of s) {                                                    
        // 处理 text_delta / toolcall_delta / done 等事件                               
    }                                                                                 
                                                                                        
    const finalMessage = await s.result();                                            
``` 

### 2. 非流式调用

```ts                                                                               
    const response = await complete(model, context);                                  
```    

## 流式事件模型

流式调用会产生标准事件。                                                            
                                                                                     
常见事件：                                                                                                                                                        
```text                                                                             
    start                                                                             
    text_start                                                                        
    text_delta                                                                        
    text_end                                                                          
    thinking_start                                                                    
    thinking_delta                                                                    
    thinking_end                                                                      
    toolcall_start                                                                    
    toolcall_delta                                                                    
    toolcall_end                                                                      
    done                                                                              
    error                                                                             
```                                                                                 
                                                                                     
 其中最关键的是：                                                                    
                                                                                     
 ┌────────────────┬──────────────────────────┐                                       
 │ 事件           │ 含义                     │                                       
 ├────────────────┼──────────────────────────┤                                       
 │ text_delta     │ 模型正在输出文本         │                                       
 ├────────────────┼──────────────────────────┤                                       
 │ toolcall_delta │ 模型正在生成工具调用参数 │                                       
 ├────────────────┼──────────────────────────┤                                       
 │ toolcall_end   │ 工具调用参数生成完成     │                                       
 ├────────────────┼──────────────────────────┤                                       
 │ done           │ 模型生成完成             │                                       
 ├────────────────┼──────────────────────────┤                                       
 │ error          │ 出错或中止               │                                       
 └────────────────┴──────────────────────────┘                                       
                                                                                     
这个事件模型后面会被 packages/agent 包装成更高层的 Agent 事件。                    

## 工具调用流程

以下为手写的工具执行循环:

```text                                                                             
   调用模型                                                                          
     ↓                                                                               
   得到 assistant message                                                            
     ↓                                                                               
   检查 content 中是否有 toolCall                                                    
     ↓                                                                               
   执行对应工具                                                                      
     ↓                                                                               
   追加 toolResult 到 context.messages                                               
     ↓                                                                               
   再次调用模型                                                                      
 ```

这正是 Agent Loop 的雏形.

后面 agent 章节中会把这套流程自动化.

## 工具参数校验

工具参数使用 TypeBox 定义 schema。                                                  
                                                                                     
如果你自己写 tool execution loop，需要手动校验：                                    
                                                                                     
 ```ts                                                                               
   const validatedArgs = validateToolCall(tools, toolCall);                          
 ```                                                                                 
                                                                                     
 但如果使用 agentLoop，工具参数会自动校验。                                          
                                                                                     
 这点很重要：                                                                        
                                                                                     
 ```text                                                                             
   packages/ai 提供校验能力                                                          
   packages/agent 使用它实现安全的工具执行                                           
 ```                                                       

## 能力: 多模态输入

 如果模型支持 image，可以传图片：                                                    
                                                                                     
 ```ts                                                                               
   {                                                                                 
     type: "image",                                                                  
     data: base64Image,                                                              
     mimeType: "image/png"                                                           
   }                                                                                 
 ```                                                                                 
                                                                                     
 模型是否支持图片可以这样判断：                                                          
                                                                                     
 ```ts                                                                               
   model.input.includes("image")                                                     
 ```  

## 能力: 支持 Thinking / Reasoning

 部分模型支持.

 可以用统一参数:

 ```ts                                                                               
   reasoning: "medium"                                                               
 ```  

 也可以用provider-specific 参数，例如：                                             
                                                                                     
 ```ts                                                                               
   thinkingEnabled                                                                   
   thinkingBudgetTokens                                                              
   reasoningEffort                                                                   
 ```              

  thinking 内容也会作为流式事件返回：                                                 
                                                                                     
 ```text                                                                             
   thinking_start                                                                    
   thinking_delta                                                                    
   thinking_end                                                                      
 ```

## Stop Reason

 每个 AssistantMessage 都有 stopReason。                                             
                                                                                     
 常见值：                                                                            
                                                                                     
 ```text                                                                             
   stop      正常结束                                                                
   length    达到输出长度限制                                                        
   toolUse   模型请求工具调用                                                        
   error     生成出错                                                                
   aborted   请求被取消                                                              
 ```                                                                                 
                                                                                     
 这个字段对 Agent Loop 很重要。                                                      
                                                                                     
 比如 stopReason === "toolUse" 通常意味着：                                          
                                                                                     
 ```text                                                                             
   需要执行工具，然后继续下一轮模型调用                                              
 ```  

## 错误处理与中止
                                                                                     
 流式调用出错时，不是直接抛异常，而是产生 error 事件，并且最终 message 会包含：      
                                                                                     
 ```text                                                                             
   stopReason: "error" 或 "aborted"                                                  
   errorMessage                                                                      
   partial content                                                                   
   usage                                                                             
 ```                                                                                 
                                                                                     
 这对 Agent 很重要，因为 Agent 可以：                                                
                                                                                     
 - 保留部分输出                                                                      
 - 记录上下文                                                                        
 - 支持中断后继续                                                                    
 - 做错误恢复

## Provider / Model 系统 (略)

Pi 把 provider 和 model 做成了可查询, 可类型提示的系统.

## Custom Models (略)

核心是自己构造 Model 对象：

 ```ts                                                                               
   const ollamaModel = {                                                             
     id: "llama-3.1-8b",                                                             
     api: "openai-completions",                                                      
     provider: "ollama",                                                             
     baseUrl: "http://localhost:11434/v1",                                           
     ...                                                                             
   };                                                                                
 ```                                                                                 
                                                                                     
 packages/ai 不只支持官方 provider，也支持自托管模型。

## 跨 Provider Handoff (略)

Pi 支持在同一个 conversation 中切换模型。

## Context 序列化

 ```ts                                                                               
   const serialized = JSON.stringify(context);                                       
   const restored = JSON.parse(serialized);                                          
 ```                                                                                 
                                                                                     
 这意味着它天然适合：                                                                
                                                                                     
 - 保存聊天历史                                                                      
 - 实现 session                                                                      
 - 跨服务传递上下文                                                                  
 - 切换模型继续对话                                                                  
                                                                                     
 这也是后面 coding-agent 做 session 的基础。

## Auth (略)

支持两类认证: 
- API Key
- OAuth(支持登录, 刷新token等功能).

## Development (略)

支持新增自定义 provider.

## 主线

 ```text                                                                             
   Model + Context + Tools                                                           
     ↓                                                                               
   stream / complete                                                                 
     ↓                                                                               
   AssistantMessage                                                                  
     ↓                                                                               
   ToolCall / Text / Thinking                                                        
     ↓                                                                               
   ToolResult 回填 context                                                           
     ↓                                                                               
   继续调用模型                                                                      
 ```

# Python 实践驱动 Phase 规划

本阶段目标: 以 Python 实践为抓手, 逐步复刻 `packages/ai` 的核心抽象。每个 Phase 都有一个明确的实践产物, 也对应一组需要阅读的源码。

> 前置资源: 已有 Qwen API key, 可以从 Phase 4 开始接入真实模型调用。

## Phase 1: 核心类型模型

### Topic

用 Python `dataclass` / `TypedDict` 复刻 `packages/ai` 的核心数据结构。

### 简述内容

实现最小版本的:

- `Model`
- `Context`
- `UserMessage`
- `AssistantMessage`
- `ToolResultMessage`
- `Tool`
- `ToolCall`
- `TextContent`
- `ThinkingContent`
- `ImageContent`
- `Usage`
- `StopReason`

目标不是完整复刻 TypeScript 类型, 而是把 message / context / tool 的关系写清楚。

### 能学到的技能

- 理解 LLM 应用中的核心数据模型。
- 理解 `Context` 为什么适合被 JSON 序列化。
- 理解 assistant message 为什么要用 content block 列表。
- 理解 tool call 和 tool result 如何通过 `toolCallId` 关联。

### 对应阅读源码

```text
packages/ai/src/types.ts
```

重点阅读:

```text
Model
Context
Message
UserMessage
AssistantMessage
ToolResultMessage
Tool
ToolCall
AssistantMessageEvent
Usage
StopReason
```

### 建议产物

```text
study_area/01_ai/python_practice/phase_01_types.py
```

---

## Phase 2: Fake Streaming Provider

### Topic

用 Python 实现一个假的模型流式输出函数, 模拟 `stream()` 的事件模型。

### 简述内容

实现一个 `fake_stream(context)` 生成器, 依次 yield:

```text
start
text_start
text_delta
text_end
toolcall_start
toolcall_delta
toolcall_end
done
```

可以先模拟一个固定回答:

```text
用户问: 现在几点?
模型先输出一段文本, 然后发起 get_time 工具调用。
```

### 能学到的技能

- 理解为什么流式接口不是直接返回字符串。
- 理解 `text_delta` / `toolcall_delta` 的意义。
- 理解 partial message 如何逐步形成 final assistant message。
- 为后续理解 `packages/agent/src/agent-loop.ts` 中的 `message_update` 打基础。

### 对应阅读源码

```text
packages/ai/src/stream.ts
packages/ai/src/utils/event-stream.ts
packages/ai/src/providers/faux.ts
packages/ai/test/faux-provider.test.ts
```

重点理解:

```text
stream()
complete()
streamSimple()
completeSimple()
AssistantMessageEventStream
```

### 建议产物

```text
study_area/01_ai/python_practice/phase_02_fake_stream.py
```

---

## Phase 3: 最小 Tool Calling Loop

### Topic

用 Python 手写一次:

```text
assistant toolCall → 本地执行工具 → 追加 toolResult → 再次调用模型
```

工具场景改为:

```text
让模型请求读取当前项目的文件 tree, 然后基于 tree 和学习目录推测当前学习进度。
```

### 简述内容

实现一个本地工具:

```text
list_project_tree(root: str = ".", max_depth: int = 3)
```

工具返回当前项目的目录结构, 可重点包含:

```text
study_area/
learning/
packages/ai/src/
packages/agent/src/
```

然后写一个最小循环:

1. 构造 `Context`。
2. 调用 fake model, 让它产生 `list_project_tree` 的 `ToolCall`。
3. 检查 assistant message 中是否包含 `ToolCall`。
4. 执行 `list_project_tree`。
5. 将文件 tree 作为 `ToolResultMessage` 追加到 `context.messages`。
6. 再调用 fake model, 输出对当前学习进度的推测。

### 能学到的技能

- 理解 tool calling 的完整闭环。
- 理解 `toolCallId` 的作用。
- 理解 `ToolResultMessage` 为什么也是一种 message。
- 理解工具结果如何把外部环境信息注入上下文。
- 理解 `packages/ai` 和 `packages/agent` 的边界: `ai` 提供结构, `agent` 自动化循环。

说明:

Phase 3 仍然可以先用 fake model, 重点是练习 tool loop。真实 Qwen 根据文件 tree 推测学习进度, 可以放到 Phase 6 的真实 tool calling 中实现。

### 对应阅读源码

```text
packages/ai/README.md
packages/ai/src/types.ts
packages/ai/src/utils/validation.ts
packages/ai/test/validation.test.ts
```

重点理解:

```text
Tool
ToolCall
ToolResultMessage
validateToolCall
validateToolArguments
```

### 建议产物

```text
study_area/01_ai/python_practice/phase_03_tool_loop.py
```

---

## Phase 4: Qwen 非流式调用

### Topic

用 Python 调用 Qwen 的 OpenAI-compatible API, 实现一个真实的 `complete()`。

### 简述内容

使用你已有的 Qwen API key, 写一个最小 Python 脚本:

1. 从环境变量读取 API key。
2. 构造 OpenAI-compatible chat completion 请求。
3. 发送 user message。
4. 解析 assistant response。
5. 保存到本地 `context.json`。

建议环境变量命名:

```text
QWEN_API_KEY
```

如果使用 DashScope OpenAI-compatible endpoint, 通常会涉及:

```text
base_url
model
api_key
messages
```

### 能学到的技能

- 理解 Pi 中 custom model / OpenAI-compatible API 的意义。
- 理解真实 provider 和统一抽象之间的映射关系。
- 理解 `Context` 如何落地到 provider payload。
- 初步掌握 API key 管理。
- provider response 如何转换回 AssistantMessage                       
- 为什么 Model.base_url / provider / api 有意义 

### 对应阅读源码

```text
packages/ai/src/stream.ts
packages/ai/src/providers/openai-completions.ts
packages/ai/src/providers/transform-messages.ts
packages/ai/src/env-api-keys.ts
```

重点理解:

```text
Model.baseUrl
Model.provider
Model.api
StreamOptions.apiKey
getEnvApiKey
provider payload transform
```

### 建议产物

```text
study_area/01_ai/python_practice/phase_04_qwen_complete.py
study_area/01_ai/python_practice/context.json
```

---

## Phase 5: Qwen 流式调用

### Topic

在 Phase 4 基础上, 用 Python 实现 Qwen 的 streaming 输出。

### 简述内容

实现一个 `qwen_stream(context)`:

1. 开启 stream 模式。
2. 逐 chunk 接收模型输出。
3. 转换成自己定义的统一事件:

```text
start
text_start
text_delta
text_end
done
error
```

如果暂时不处理 tool call, 只处理文本流即可。

### 能学到的技能

- 理解 provider 原始 streaming 协议和 Pi 标准事件之间的转换。
- 理解为什么 `packages/ai` 要为不同 provider 写 adapter。
- 理解流式 UI / CLI 输出的底层机制。
- 为后续理解 `AssistantMessageEvent` 打基础。

### 对应阅读源码

```text
packages/ai/src/providers/openai-completions.ts
packages/ai/src/utils/event-stream.ts
packages/ai/src/stream.ts
packages/ai/test/stream.test.ts
```

重点理解:

```text
provider stream → AssistantMessageEvent
text_delta
done
error
stream.result()
```

### 建议产物

```text
study_area/01_ai/python_practice/phase_05_qwen_stream.py
```

---

## Phase 6: Qwen 真实 Tool Calling

### Topic

让 Qwen 真实产生 tool call, 然后由 Python 执行本地工具并回填 tool result。

### 简述内容

实现一个工具:

```text
list_project_tree(root?: string, max_depth?: number)
```

工具读取当前项目目录结构。用户让模型判断当前学习进度, 模型应主动调用该工具获取项目 tree, 再基于工具结果给出判断。

向 Qwen 请求时传入 tools/function schema, 让模型决定是否调用工具。

流程:

1. 用户问: `请根据当前项目文件结构, 判断我在 agent 应用开发学习计划中进展到哪里了。`
2. 请求中带上 `list_project_tree` 工具定义。
3. Qwen 返回 tool call。
4. Python 校验参数, 限制 root / max_depth, 避免读取过大范围。
5. Python 执行 `list_project_tree`。
6. 将文件 tree 作为 tool result 追加到 messages。
7. 再次请求 Qwen。
8. 得到模型对当前学习进度的判断和下一步建议。

### 能学到的技能

- 理解真实 tool calling payload。
- 理解工具 schema 如何影响模型行为。
- 理解参数校验和工具权限边界的重要性。
- 理解工具结果如何把本地环境信息注入模型上下文。
- 理解 Agent Loop 的最小闭环。

### 对应阅读源码

```text
packages/ai/src/types.ts
packages/ai/src/utils/validation.ts
packages/ai/src/providers/openai-completions.ts
packages/ai/test/tool-call-without-result.test.ts
packages/ai/test/openai-completions-tool-choice.test.ts
```

重点理解:

```text
Tool.parameters
ToolCall.arguments
ToolResultMessage
validateToolCall
stopReason: "toolUse"
```

### 建议产物

```text
study_area/01_ai/python_practice/phase_06_qwen_tool_call.py
```

---

## Phase 7: Context 持久化与恢复

### Topic

把 Python 中的 `Context` 保存到 JSON 文件, 下次运行时恢复并继续对话。

### 简述内容

实现:

1. `save_context(context, path)`
2. `load_context(path)`
3. 每次模型响应后自动保存。
4. 下次启动读取历史 messages。
5. 支持继续追问。

### 能学到的技能

- 理解为什么 Pi 的 `Context` 设计成容易 JSON 序列化。
- 理解 session / conversation persistence 的基础。
- 为后续学习 `packages/coding-agent` 的 session manager 做准备。

### 对应阅读源码

```text
packages/ai/README.md
packages/ai/src/types.ts
packages/coding-agent/src/core/session-manager.ts
```

当前阶段重点读前两个, `session-manager.ts` 可以先粗略浏览。

### 建议产物

```text
study_area/01_ai/python_practice/phase_07_context_persistence.py
study_area/01_ai/python_practice/context.json
```

---

## Phase 8: Mini `pi-ai` Python 版封装

### Topic

把前面的代码整理成一个小型 Python SDK。

### 简述内容

整理出类似 `packages/ai` 的最小 API:

```python
model = get_model("qwen", "qwen-plus")
context = Context(...)

message = complete(model, context)

for event in stream(model, context):
    ...
```

支持:

- fake provider
- qwen provider
- complete
- stream
- tools
- context save/load

### 能学到的技能

- 理解 SDK 层抽象设计。
- 理解 provider registry 的意义。
- 理解统一接口如何屏蔽不同 provider 差异。
- 为后续进入 `packages/agent` 打基础。

### 对应阅读源码

```text
packages/ai/src/api-registry.ts
packages/ai/src/models.ts
packages/ai/src/models.generated.ts
packages/ai/src/stream.ts
packages/ai/src/providers/register-builtins.ts
```

重点理解:

```text
getModel
getModels
getProviders
registerApiProvider
resolveApiProvider
```

### 建议产物

```text
study_area/01_ai/python_practice/mini_pi_ai/
  __init__.py
  types.py
  registry.py
  providers/
    fake.py
    qwen.py
  stream.py
  tools.py
  persistence.py
```

---

## Phase 执行顺序

```text
Phase 1: 核心类型模型
  ↓
Phase 2: Fake Streaming Provider
  ↓
Phase 3: 最小 Tool Calling Loop
  ↓
Phase 4: Qwen 非流式调用
  ↓
Phase 5: Qwen 流式调用
  ↓
Phase 6: Qwen 真实 Tool Calling
  ↓
Phase 7: Context 持久化与恢复
  ↓
Phase 8: Mini pi-ai Python SDK
```

## 01_ai 完成标准

完成全部 Phase 后, 应该能够用 Python 解释并实现以下主线:

```text
Model + Context + Tools
  ↓
complete / stream
  ↓
AssistantMessage
  ↓
ToolCall / Text / Thinking
  ↓
ToolResult 回填 Context
  ↓
继续调用模型
```

完成这些 Phase 后, 再进入 `packages/agent`, 重点学习如何把上述手写循环升级为通用 Agent Loop。
