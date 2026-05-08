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
