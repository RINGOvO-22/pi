# pi-feishu-bridge-sdk

SDK 版 bridge 设计：使用 TypeScript 在同一个 Node.js 进程里连接飞书，并直接嵌入 pi coding agent。

## 1. 方案定位

这里的 SDK 方案同时使用两个 SDK：

```text
@larksuiteoapi/node-sdk                 飞书官方 Node SDK
@earendil-works/pi-coding-agent        pi SDK
```

和 CLI / RPC 版的区别：

```text
CLI 版：bridge → pi -p 子进程
RPC 版：bridge → pi --mode rpc 子进程 → JSONL
SDK 版：bridge → createAgentSession() → AgentSession
```

SDK 版不需要启动 pi 子进程，也不需要维护 JSONL 协议。它适合作为长期主线。

飞书侧优先使用：

```typescript
import { createLarkChannel } from "@larksuiteoapi/node-sdk";
```

`Channel` 是飞书官方 Node SDK 面向对话机器人的高层模块。它封装了底层 `WSClient` / `EventDispatcher` / `Client`，并提供消息归一化、安全策略、发送、流式回复、媒体上传和卡片交互。

只有在排查底层长连接问题时，再直接使用 `WSClient` / `EventDispatcher`。

## 2. 第一版范围

第一版 SDK bridge 只做：

- 使用一个全局 `AgentSession`。
- 使用 `createLarkChannel()` 建立飞书长连接并接收归一化文本消息。
- 使用 Channel 内置安全策略，并在应用队列层保留 `message_id` 幂等检查。
- 收到事件后快速入队。
- 串行执行 `session.prompt()`。
- 聚合 assistant 最终文本。
- 调用飞书消息 API 回复。
- 支持 `/help`、`/status`、`/abort`、`/new`。

第一版暂不做：

- 多用户 session 隔离。
- 群聊复杂权限控制。
- 附件处理。
- 消息卡片。
- 高频流式更新飞书消息。
- extension UI 映射。
- session 恢复、切换和 fork。

## 3. 目标链路

```text
飞书用户
  ↓
飞书长连接事件 im.message.receive_v1
  ↓
createLarkChannel()
  ↓
校验、去重、入队，并尽快返回
  ↓
task queue
  ↓
AgentSession.prompt()
  ↓
message_update / agent_end
  ↓
聚合最终文本
  ↓
飞书 reply API
```

飞书官方 Node SDK 的底层长连接文档说明：事件需要在 3 秒内完成处理，否则会触发超时重推。因此，Channel 的消息监听器里不要直接等待 pi 完成任务。

## 4. 建议结构

```text
study_area/feishu/pi-feishu-bridge-sdk/
  README.md
  package.json
  tsconfig.json
  .env.example
  .gitignore

  src/
    main.ts                 程序入口
    config.ts               环境变量

    feishu/
      channel.ts            创建和配置 LarkChannel
      events.ts             接收归一化事件、校验、入队
      messenger.ts          封装 channel.send() / channel.stream()

    pi/
      session.ts            创建 AgentSession
      session-registry.ts   后续按 session key 管理 AgentSession
      events.ts             聚合 pi 事件和 assistant 文本

    app/
      bridge.ts             队列消费和核心流程
      commands.ts           /help /new /abort /status
      task-queue.ts         按会话串行执行任务

  tests/
    minimal-sdk.ts          不接飞书，只验证 pi SDK
```

## 5. 环境变量

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
PI_WORKDIR=/home/ringo/workspace/pi-feishu-workspace
PI_SESSION_DIR=/home/ringo/workspace/pi-feishu-sessions
PI_AGENT_DIR=/home/ringo/.pi/agent
PI_TASK_TIMEOUT_SECONDS=300
```

说明：

- `PI_WORKDIR`：pi 可以读取和修改的工作目录，不要直接指向整个 home 目录。
- `PI_SESSION_DIR`：SDK bridge 专用 session 存储目录。
- `PI_AGENT_DIR`：pi 的配置、模型和认证目录。第一版可以复用已有 `~/.pi/agent`。
- `.env` 只放本机，不要提交到 git。

## 6. pi SDK 最小验证

先不接飞书。创建 `tests/minimal-sdk.ts`，只验证 pi SDK 能跑通：

```typescript
import { join } from "node:path";
import {
  AuthStorage,
  createAgentSession,
  ModelRegistry,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const agentDir = process.env.PI_AGENT_DIR!;
const authStorage = AuthStorage.create(join(agentDir, "auth.json"));
const modelRegistry = ModelRegistry.create(authStorage, join(agentDir, "models.json"));
const sessionManager = SessionManager.create(
  process.env.PI_WORKDIR!,
  process.env.PI_SESSION_DIR!,
);

const { session } = await createAgentSession({
  cwd: process.env.PI_WORKDIR,
  agentDir,
  authStorage,
  modelRegistry,
  sessionManager,
});

let finalText = "";
const unsubscribe = session.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    finalText += event.assistantMessageEvent.delta;
  }
});

await session.prompt("只回复 OK");
console.log(finalText);

unsubscribe();
session.dispose();
```

验收标准：

- 能创建 `AgentSession`。
- 能复用已有 pi 认证。
- 能执行 `session.prompt("只回复 OK")`。
- 能从 `message_update` 收集 `text_delta`。
- 最终输出包含 `OK`。
- 脚本退出前调用 `unsubscribe()` 和 `session.dispose()`。

注意：实现时需要检查实际类型定义，不要直接复制示例后假设路径参数完全正确。

## 7. 第一版 session 管理

第一版只维护一个全局 session：

```text
global AgentSession
global task queue
```

飞书消息按顺序进入队列。队列消费者每次只执行一个 `session.prompt()`。

这样做的好处：

- 最容易验证 SDK 链路。
- 不会让多个 prompt 同时修改一个 session。
- `/abort` 可以直接调用当前 session 的 `abort()`。

限制：

- 不同飞书用户会共享上下文。
- 只适合个人原型，不适合多人使用。

## 8. 多用户演进

基础链路稳定后，再增加 session registry：

```text
session key = tenant_key + chat_id + user_id
```

每个 key 对应：

```typescript
interface SessionHolder {
  session: AgentSession;
  unsubscribe: () => void;
  queue: TaskQueue;
  lastActiveAt: number;
}
```

需要补充：

- 每个 holder 串行执行任务。
- 空闲 session 定时 `dispose()`。
- bridge 退出时统一 `dispose()`。
- 限制同时活跃 session 数量。
- 使用专门目录持久化 session。

## 9. 命令映射

```text
/help      bridge 直接返回帮助文本
/status    返回 isStreaming、队列长度、sessionId
/abort     调用 session.abort()
/new       dispose() 旧 session，创建新的 AgentSession
/compact   调用 session.compact()
```

第一版 `/new` 直接重建 `AgentSession` 即可。

后续如果要支持恢复历史会话、切换 session 或 fork，再使用：

```text
createAgentSessionRuntime()
AgentSessionRuntime
```

不要在第一版提前引入 runtime。

## 10. 流式输出策略

pi SDK 可以通过 `message_update` 获得 `text_delta`。飞书里不适合每个 delta 都发送一次请求。

第一版：

```text
只聚合 delta
任务完成后回复最终文本
```

后续使用 `channel.stream()`：

```text
把 pi 的 text_delta 追加到 stream controller
由 Channel 负责飞书侧流式回复和节流
任务完成后结束 stream
```

## 11. 实施顺序

### 1. 跑通最小 SDK 验证

目标：不接飞书，只验证 `createAgentSession()`、事件订阅、`prompt()` 和 `dispose()`。

### 2. 跑通飞书 Node SDK 固定回复

目标：不接 pi，使用 `createLarkChannel()` 接收文本消息，入队后回复固定文本。

如果连接失败，再单独写一个 `WSClient` / `EventDispatcher` 最小脚本排查底层问题。

### 3. 串联飞书和 pi SDK

目标：飞书消息入队后调用 `session.prompt()`，完成后回复最终文本。

### 4. 增加命令

目标：支持 `/help`、`/status`、`/abort`、`/new`。

### 5. 增加多用户 session registry

目标：不同飞书用户或群聊使用独立 session，并释放长期空闲 session。

### 6. 增加节流后的状态更新

目标：长任务可以看到状态，但不会在飞书里刷屏。

## 12. 与 RPC 版的取舍

SDK 版优点：

- 不需要启动和维护 pi 子进程。
- 不需要解析 JSONL。
- 可以直接调用 `prompt()`、`abort()`、`compact()`。
- 可以直接订阅 pi 事件。
- 可以复用飞书 Channel 的消息归一化、安全策略和流式回复。
- 更适合 TypeScript bridge 长期维护。

SDK 版限制：

- bridge 必须使用 Node.js / TypeScript。
- 需要自己管理 `AgentSession` 生命周期。
- 多用户版本需要自己实现 session registry。

RPC 版仍然有价值：

- Python 等非 Node.js 程序可以复用。
- bridge 和 pi 进程隔离，单个 pi 进程退出时更容易单独重启。
- 可以继续作为协议验证和故障排查工具。

## 13. 参考

- pi SDK：`packages/coding-agent/docs/sdk.md`
- pi SDK examples：`packages/coding-agent/examples/sdk/`
- 飞书官方 Node SDK：https://github.com/larksuite/node-sdk
- 飞书长连接文档：https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case?lang=zh-CN
