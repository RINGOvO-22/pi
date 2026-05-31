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

1. 跑通 `tests/minimal_rpc.py`。
2. 复制 CLI 版的飞书长连接、事件解析、消息回复模块。
3. 新增 `pi_rpc/process.py`，启动 `PI_COMMAND --mode rpc`。
4. 新增 JSONL reader/writer。注意不要按 Unicode line separator 拆行，只按 `\n` 处理。
5. 发送最小 prompt 请求：

   ```json
   {"id":"req-1","type":"prompt","message":"Hello"}
   ```

6. 收集 RPC 返回事件，先只取最终 assistant 文本。
7. 回复飞书。
8. 再增加 `/new`、`/abort`、`/status`。

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
