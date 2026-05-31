# pi-feishu-bridge-rpc

RPC 版 bridge 计划：使用飞书长连接接收消息，并使用常驻 pi RPC 子进程处理对话。

## 目标

CLI 版每条消息都会执行一次：

```bash
pi -p "用户消息"
```

这会导致：

- 每条消息都是单轮对话。
- 每次都有 pi CLI 冷启动成本。
- 不方便支持 `/abort`、session、流式进度。

RPC 版目标是：bridge 启动时只启动一次 pi RPC 进程：

```bash
pi --mode rpc
```

后续每条飞书消息通过 JSONL 协议发送给这个常驻进程。

## 目标链路

```text
飞书用户
  ↓
飞书长连接事件 im.message.receive_v1
  ↓
pi-feishu-bridge-rpc
  ↓ JSONL stdin/stdout
pi --mode rpc 常驻进程
  ↓
pi session / tools / workspace
  ↓
pi-feishu-bridge-rpc
  ↓
飞书 reply API
飞书消息回复
```

## 初版范围

第一版 RPC bridge 只做：

- 使用飞书长连接接收文本消息。
- 按 `message_id` 去重。
- 启动一个全局 pi RPC 子进程。
- 把飞书文本消息发送成 RPC `prompt` 请求。
- 从 RPC 事件里收集 assistant 最终文本。
- 回复到飞书。

## 暂不做

- 多用户多 session 隔离。
- 群聊复杂权限控制。
- 附件处理。
- 消息卡片。
- 流式编辑飞书消息。
- extension UI 映射。

## 建议结构

```text
study_area/feishu/pi-feishu-bridge-rpc/
  README.md
  requirements.txt
  .env.example
  .gitignore

  src/
    main.py                 程序入口
    config.py               环境变量
    logging_config.py       日志配置

    feishu/
      client.py             飞书 OpenAPI client
      events.py             飞书事件解析
      messenger.py          回复飞书消息

    pi_rpc/
      process.py            启动和管理 pi --mode rpc 子进程
      protocol.py           JSONL 编解码、请求 ID、事件分发
      session.py            后续 session 管理

    app/
      bridge.py             飞书消息 → RPC prompt → 飞书回复
      commands.py           /help /new /abort /status
```

## 环境变量

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
PI_COMMAND=/home/ringo/.nvm/versions/node/v22.22.2/bin/pi
PI_WORKDIR=/home/ringo/workspace/pi-feishu-workspace
PI_SESSION_DIR=/home/ringo/workspace/pi-feishu-sessions
PI_RPC_TIMEOUT_SECONDS=300
```

## 最小 RPC 验证

先不接飞书，先验证 Python 能启动 `pi --mode rpc`，发送一条 prompt，并读取 assistant 输出。

测试脚本：

```text
tests/minimal_rpc.py
```

运行：

```bash
cd /home/ringo/workspace/pi/study_area/feishu/pi-feishu-bridge-rpc
/home/ringo/miniforge3/envs/pi/bin/python tests/minimal_rpc.py "只回复 OK"
```

预期输出：

```text
OK

--- final text ---
OK
```

这个脚本会：

1. 读取 `.env`。
2. 启动 `PI_COMMAND --mode rpc --session-dir PI_SESSION_DIR`。
3. 向 stdin 写入 JSONL prompt：

   ```json
   {"id":"req-...","type":"prompt","message":"只回复 OK"}
   ```

4. 从 stdout 读取 JSONL 事件。
5. 拼接 `message_update.assistantMessageEvent.text_delta`。
6. 遇到 `agent_end` 后退出。

## 实施顺序

### 1. 跑通最小 RPC 验证

状态：已完成。

目标：先不接飞书，只验证 Python 能启动 `pi --mode rpc`，发送 prompt，并读到 assistant 输出。

使用脚本：

```bash
/home/ringo/miniforge3/envs/pi/bin/python tests/minimal_rpc.py "只回复 OK"
```

验收标准：

- 能启动 pi RPC 子进程。
- 能写入一条 JSONL prompt。
- 能收到 `response`。
- 能从 `message_update` 里拼接 `text_delta`。
- 能在 `agent_end` 后结束。

### 2. 复制飞书基础模块

状态：已完成。

目标：复用 CLI 版已经跑通的飞书长连接能力。

从 `pi-feishu-bridge-cli` 复制或改造这些模块：

```text
src/config.py
src/logging_config.py
src/feishu/client.py
src/feishu/events.py
src/feishu/messenger.py
src/app/commands.py
```

当前已复制到 RPC 项目：

```text
src/__init__.py
src/config.py
src/logging_config.py

src/feishu/__init__.py
src/feishu/client.py
src/feishu/events.py
src/feishu/messenger.py

src/app/__init__.py
src/app/commands.py
```

和 CLI 版相比，需要改动的地方：

#### `src/config.py`

CLI 版配置：

```python
pi_timeout_seconds: int
```

RPC 版改成：

```python
pi_session_dir: Path
pi_rpc_timeout_seconds: int
```

对应环境变量：

```bash
PI_SESSION_DIR=/home/ringo/workspace/pi-feishu-sessions
PI_RPC_TIMEOUT_SECONDS=300
```

原因：RPC 版会启动常驻进程：

```bash
PI_COMMAND --mode rpc --session-dir PI_SESSION_DIR
```

不再每条消息执行：

```bash
PI_COMMAND -p "用户消息"
```

#### `src/app/commands.py`

CLI 版只是提示暂不支持 `/new`、`/abort`、`/status`。

RPC 版后续会把这些命令映射到 RPC 命令：

```json
{"type":"new_session"}
{"type":"abort"}
{"type":"get_state"}
```

所以当前文案改为：

```text
RPC 第一版暂未接入 /new、/abort、/status。
```

#### 暂时不需要改的文件

这些文件目前和 CLI 版保持一致：

```text
src/logging_config.py
src/feishu/client.py
src/feishu/events.py
src/feishu/messenger.py
```

原因：它们只处理飞书侧逻辑，不关心 pi 后端是 CLI 还是 RPC。

验收标准：

- 能读取 `.env`。
- 能创建飞书 OpenAPI client。
- 能解析 `im.message.receive_v1` 文本消息。
- 能用 reply API 回复文本。
- 能处理 `/help`。

### 3. 新增 pi RPC 进程管理

状态：已完成。

目标：bridge 启动时启动一个常驻 pi RPC 子进程。

已新增文件：

```text
src/pi_rpc/__init__.py
src/pi_rpc/process.py
tests/start_rpc_process.py
```

`PiRpcProcess` 职责：

- 使用 `PI_COMMAND` 启动：

  ```bash
  pi --mode rpc --session-dir PI_SESSION_DIR
  ```

- 设置工作目录为 `PI_WORKDIR`。
- 创建 `PI_WORKDIR` 和 `PI_SESSION_DIR`。
- 持有 `stdin` 和 `stdout`，供后续 JSONL 协议层使用。
- 读取 `stderr` 并写入日志，方便排查 pi 启动失败、认证失败、模型错误等问题。
- 提供：

  ```python
  start()
  stop()
  is_running()
  returncode()
  ```

- 支持 `with PiRpcProcess(config) as rpc_process:`，退出时自动 `stop()`。

验收脚本：

```bash
cd /home/ringo/workspace/pi/study_area/feishu/pi-feishu-bridge-rpc
/home/ringo/miniforge3/envs/pi/bin/python tests/start_rpc_process.py
```

预期：

```text
is_running: True
stdin available: True
stdout available: True
Sleeping for 3 seconds, then stopping...
is_running after stop: False
```

验收标准：

- 能启动一个 pi RPC 进程。
- 进程不随单条消息结束。
- 能拿到 stdin/stdout。
- 调用 `stop()` 后进程退出。
- 能在日志中看到 RPC 进程启动成功或失败原因。

### 4. 新增 JSONL 协议层

目标：把 RPC 的 JSONL 读写封装起来，避免业务代码直接操作 stdin/stdout。

建议文件：

```text
src/pi_rpc/protocol.py
```

职责：

- 生成请求 ID。
- 写入 JSONL 命令。
- 读取 JSONL 事件。
- 按 `\n` 分割消息。
- 接受可选 `\r\n`，读取后去掉末尾 `\r`。
- 不使用会把 Unicode line separator 当换行的通用 line reader。

最小 prompt 请求：

```json
{"id":"req-1","type":"prompt","message":"Hello"}
```

验收标准：

- 能发送 prompt。
- 能识别对应 `response.id`。
- 能识别 `message_update`。
- 能识别 `agent_end`。
- prompt 被拒绝时能返回错误。

### 5. 封装 `PiRpcClient.prompt()`

目标：给 bridge 提供一个简单接口，隐藏 RPC 细节。

建议接口：

```python
class PiRpcClient:
    def prompt(self, message: str) -> str:
        ...
```

内部流程：

```text
发送 prompt command
  ↓
等待 response success
  ↓
收集 text_delta
  ↓
遇到 agent_end
  ↓
返回最终文本
```

验收标准：

- 输入一段文本，返回 assistant 最终文本。
- 超时返回清晰错误。
- pi 报错时返回清晰错误。
- 同一时间先只允许一个 prompt 执行，避免并发读写 stdout 混乱。

### 6. 接入飞书 bridge 主流程

目标：把飞书文本消息接到 `PiRpcClient.prompt()`。

建议文件：

```text
src/app/bridge.py
src/main.py
```

主流程：

```text
收到飞书文本消息
  ↓
按 message_id 去重
  ↓
处理 /help 等本地命令
  ↓
调用 PiRpcClient.prompt(text)
  ↓
把结果 reply 到飞书
```

验收标准：

- 飞书私聊机器人发送 `你好`。
- bridge 只处理一次该 `message_id`。
- pi RPC 返回内容。
- 机器人回复最终内容。
- 不再每条消息启动一次 pi CLI。

### 7. 增加基础命令

目标：先提供最小管理能力。

优先级：

```text
/help       显示帮助
/status     查看 RPC 进程和当前任务状态
/abort      中断当前 pi 执行
/new        新建 pi session
```

对应 RPC 命令：

```json
{"type":"get_state"}
{"type":"abort"}
{"type":"new_session"}
```

验收标准：

- `/help` 不调用 pi，直接回复帮助。
- `/status` 返回当前是否执行中、session 信息。
- `/abort` 能中断当前执行。
- `/new` 能开启新 session。

### 8. 再做 session 映射

目标：让不同飞书会话逐步对应不同 pi session。

第一版先不做，RPC bridge 先使用全局一个 session。

后续设计：

```text
session key = tenant_key + chat_id + sender_open_id
```

可能策略：

- 全局一个 RPC 进程，按 session key 切换 session。
- 每个飞书会话一个 RPC 进程。
- 每个飞书会话一个 session 文件，必要时 `switch_session`。

验收标准后续再定。

## 和 CLI 版的区别

```text
pi-feishu-bridge-cli
  每条消息启动一次 pi -p
  简单，但慢、单轮

pi-feishu-bridge-rpc
  bridge 启动时启动一个 pi --mode rpc
  后续复用常驻进程
  更适合多轮、取消、状态和流式进度
```
