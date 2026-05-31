# Pi 接入飞书计划

目标：在飞书里和本机运行的 pi 交互，并预留接入 Feishu CLI / 飞书开放平台能力的扩展点。

## 1. 目标形态

### 基础目标

- 用户在飞书私聊或群聊里发送消息。
- 本机服务收到飞书事件。
- 本机服务把消息转给本机 pi agent。
- pi 执行任务后，把结果回复到飞书。

### 进阶目标

- 支持长任务状态更新：开始、执行中、完成、失败。
- 支持多会话：按飞书用户或群聊维护独立 pi session。
- 支持命令：如 `/new`、`/abort`、`/status`、`/compact`。
- 支持文件：飞书附件下载后传给 pi，pi 生成的文件可上传回飞书。
- 支持 Feishu CLI：把部分飞书操作封装成 pi tool，让 pi 主动调用飞书能力。

## 2. 推荐架构

```text
Feishu 用户
   ↓
飞书机器人 / 事件订阅
   ↓ 长连接事件通道
本机 bridge server
   ↓
Pi SDK / pi RPC / 本地 pi 子进程
   ↓
本机工作目录、tools、session
   ↓
bridge server
   ↓ Feishu OpenAPI
飞书消息回复
```

核心是写一个本机 `pi-feishu-bridge` 服务。

当前接收事件方式选择：**先采用长连接**。这适合本机开发和原型验证，不需要先准备公网 HTTPS 回调地址。后续正式上线时，再迁移到开发者服务器 webhook。

它负责：

1. 通过飞书长连接接收事件。
2. 校验事件来源和应用配置。
3. 把飞书消息转换成 pi prompt。
4. 调用本机 pi。
5. 把 pi 输出转换成飞书消息。
6. 管理用户、群聊、session、任务状态。

## 3. 接入方式选择

### 方案 A：使用 pi SDK / agent-core

优点：

- 最干净，能直接管理 Agent session。
- 可以精细控制事件、工具、流式输出、取消任务。
- 更适合长期维护。

缺点：

- 需要读 pi SDK 文档和源码。
- 需要自己处理 session 持久化和 tool 配置。

适合最终版本。

### 方案 B：本机 bridge 调用 pi CLI 子进程

示例：

```bash
node packages/coding-agent/dist/cli.js -p "用户消息"
```

优点：

- 最快能跑通。
- 不需要深挖 SDK。

缺点：

- 交互状态、流式输出、取消任务较难处理。
- 多用户并发不优雅。

适合第一版原型。

### 方案 C：接 pi RPC 模式

可行。pi 官方 RPC 文档明确说明：RPC mode 用 JSONL 协议通过 stdin/stdout 进行 headless operation，适合嵌入其他应用、IDE 或自定义 UI。

启动方式：

```bash
pi --mode rpc [options]
```

本地源码版可用：

```bash
node packages/coding-agent/dist/cli.js --mode rpc
```

bridge 作为 RPC client，启动并持有一个 pi RPC 子进程，然后通过 stdin 发送 JSONL 命令，通过 stdout 接收 response 和 event。

基础 prompt：

```json
{"id":"req-1","type":"prompt","message":"Hello"}
```

响应：

```json
{"id":"req-1","type":"response","command":"prompt","success":true}
```

真正的 assistant 输出通过事件流返回，例如 `message_update` / `agent_end`。

优点：

- 比 CLI print mode 更适合常驻 bridge。
- 支持流式事件，可映射到飞书长任务进度。
- 支持 `abort`、`new_session`、`get_state`、`get_messages`、`switch_session`、`compact`、`get_session_stats`。
- 支持 extension UI protocol，可把扩展里的 confirm/select/input 映射成飞书交互。
- 可以用 `--session-dir` 指定独立 session 存储。

缺点：

- RPC 是 JSONL 协议，需要自己写 client。
- stdout 里同时有 response 和 event，需要按 `id` 和 `type` 分发。
- 文档强调不能用 Node `readline` 解析协议，因为它会把 Unicode line separators 当换行；需要按 `\n` 手写 JSONL reader。
- 飞书消息不适合高频流式刷屏，需要节流/聚合。

适合作为主线方案。第一版可以先用一个 RPC 进程对应一个 bridge，再逐步演进为每个飞书会话独立 RPC 进程或独立 session。

## 4. Feishu 侧准备

### 4.1 大致流程介绍

这一章只解决一件事：让飞书机器人能把消息送到你的本机程序，并允许本机程序把回复发回飞书。

当前选择：**长连接接收事件**。

可以理解为：不是飞书来访问你的服务器，而是你的本机程序主动连到飞书。

```text
本机 bridge 程序启动
   ↓
bridge 使用飞书官方 SDK 连接飞书开放平台
   ↓
飞书后台显示“长连接已连接”
   ↓
用户给机器人发消息
   ↓
飞书通过长连接把消息事件推给 bridge
   ↓
bridge 调用本机 pi
   ↓
bridge 调用飞书消息 API，把 pi 的回答发回飞书
```

所以飞书后台里说的：

> 无需注册公网域名或配置加密策略，仅需使用官方 SDK 启动长连接飞书客户端，并确保连接成功后，即可开启该模式。配置完成后，可点击按钮验证连接状态。

意思是：

1. 你不用填 webhook URL。
2. 你不用准备公网域名。
3. 你不用先配置 HTTPS。
4. 你需要先在本机跑起来一个使用飞书官方 SDK 的 bridge 程序。
5. bridge 连上飞书后，你再回到飞书后台点“验证连接状态”。
6. 验证成功后，飞书才确认你的长连接客户端在线。

第一版暂时不需要：

- 公网服务器
- HTTPS 域名
- webhook URL
- ngrok / localtunnel / cloudflared / frp
- 事件加密策略

第一版会用到这些飞书能力：

- 接收消息事件：`im.message.receive_v1`
- 回复某一条消息：`POST /open-apis/im/v1/messages/:message_id/reply`
- 主动发送消息：`POST /open-apis/im/v1/messages`
- 调用消息 API 时使用应用的 `tenant_access_token`

### 4.2 步骤

按这个顺序做。

#### 第 1 步：打开飞书开放平台

地址：

```text
https://open.feishu.cn/
```

使用你的飞书账号登录。

#### 第 2 步：创建企业自建应用

创建一个企业自建应用，例如：

```text
pi-feishu-bridge-toy
```

这个应用后面就是你的飞书机器人。

#### 第 3 步：记录应用凭证

在应用后台找到并保存：

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

第一版长连接最关键的是这两个值。

如果页面上还有这些值，也一并记录，但第一版可以先不启用加密：

```bash
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
```

说明：

- `APP_ID`：应用 ID。
- `APP_SECRET`：应用密钥，bridge 用它获取飞书访问 token。
- `VERIFICATION_TOKEN`：用于事件来源校验，按 SDK 需要再接入。
- `ENCRYPT_KEY`：事件加密密钥。第一版不启用事件加密时可以留空。

这些值只能放在本机 `.env`，不要提交到 git。

#### 第 4 步：开启机器人能力

在应用后台开启“机器人”能力。

不开启机器人能力的话，用户无法像聊天一样给这个应用发消息。

#### 第 5 步：配置事件接收方式为长连接

在应用后台找到“事件与回调”或“事件订阅”。

选择事件接收方式：

```text
长连接
```

这里不要选择 webhook，也不要填写请求地址。

#### 第 6 步：创建最小 bridge 程序

如果你是第一次做到这里，**此时还没有 bridge 程序**。

所以这里要先插入一步：创建一个最小版 bridge。它暂时不需要调用 pi，也不需要回复消息，只需要完成一件事：用飞书官方 SDK 连上飞书长连接。

最小 bridge 要做的事情：

1. 读取 `.env` 里的 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`。
2. 使用飞书官方 SDK 创建长连接客户端。
3. 启动长连接。
4. 打印日志，例如：`Feishu long connection started`。
5. 保持进程运行，不要立刻退出。

建议目录：

```text
study_area/feishu/pi-feishu-bridge-toy/
```

做到这一步的目标不是完整机器人，而是让飞书后台能验证：你的本机确实有一个客户端连上来了。

#### 第 7 步：启动本机 bridge 长连接客户端

创建好最小 bridge 后，在本机启动它。

这个程序会使用下面两个配置连接飞书：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

程序启动成功后，它会一直运行，保持和飞书的连接。

#### 第 8 步：在飞书后台验证连接状态

本机 bridge 启动后，回到飞书开放平台页面，点击类似下面的按钮：

```text
验证连接状态
```

预期结果：飞书后台提示连接成功。

如果验证失败，通常说明：

- bridge 程序没有启动。
- `APP_ID` 或 `APP_SECRET` 配错了。
- 当前应用和 bridge 使用的应用不是同一个。
- 本机网络无法连接飞书开放平台。

#### 第 9 步：订阅消息事件

连接验证成功后，订阅事件：

```text
im.message.receive_v1
```

这个事件表示：用户私聊机器人，或在群里 @ 机器人时，飞书会把消息推给 bridge。

#### 第 10 步：申请消息权限

第一版至少需要这些权限：

- 读取用户发给机器人的单聊消息
- 接收群聊中 @ 机器人的消息
- 以应用身份发送消息

如果飞书后台提示还缺权限，按提示补齐。

权限修改后，记得发布或生效应用配置。

#### 第 11 步：把机器人加入测试环境

建议先用私聊测试：

```text
你 → 私聊机器人 → bridge 收到消息 → pi 生成回复 → 机器人回复你
```

私聊跑通后，再把机器人拉进测试群。

#### 第 12 步：准备本机 `.env`

后续 bridge 项目目录里准备 `.env`：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
PI_COMMAND=/home/ringo/.nvm/versions/node/v22.22.2/bin/pi
PI_WORKDIR=/home/ringo/workspace/pi-feishu-workspace
```

注意：

- `.env` 只放本机。
- 不要提交到 git。
- 第一版可以先让 `FEISHU_ENCRYPT_KEY` 留空。
- `PI_WORKDIR` 建议使用专门目录，不要直接指向整个 home 目录。

### 4.3 扩展项

下面这些不是第一版必须做的。

#### 事件加密

第一版先不启用事件加密，降低复杂度。

后续如果要启用，需要：

- 在飞书后台配置加密策略。
- 保存 `FEISHU_ENCRYPT_KEY`。
- bridge 对收到的事件做解密。

#### 群聊支持

第一版建议先只测私聊。

后续支持群聊时，需要处理：

- 只有 @ 机器人时才响应。
- 不同群、不同用户的 session 隔离。
- 长任务进度不要在群里刷屏。

#### 文件和图片

后续可以支持：

- 用户发文件给机器人。
- bridge 下载附件。
- pi 读取文件。
- pi 生成文件。
- bridge 上传文件回飞书。

这需要额外申请文件上传、下载权限。

#### 白名单

建议后续增加白名单，只允许指定用户或群使用机器人：

```json
{
  "allowedUserIds": ["ou_xxx"],
  "allowedChatIds": ["oc_xxx"]
}
```

这样可以避免任何人都能让你的本机 pi 执行任务。

#### 从长连接迁移到 webhook

长连接适合本机开发和原型验证。

如果以后部署到服务器，推荐迁移到开发者服务器 webhook：

- 稳定性更好。
- 更适合生产部署。
- 更容易横向扩容。
- 不依赖本机进程一直保持长连接。

## 5. bridge server 设计

bridge 项目按阶段拆分，避免把验证代码、CLI 原型和 RPC 原型混在一起：

```text
study_area/feishu/pi-feishu-bridge-toy/   # Chapter 4：验证飞书长连接和固定回复
study_area/feishu/pi-feishu-bridge-cli/   # Chapter 5：CLI 单轮原型，每条消息执行一次 pi -p
study_area/feishu/pi-feishu-bridge-rpc/   # Chapter 6：RPC 常驻进程原型，下一步主线
```

当前已完成 CLI 版原型，下一步转向 RPC 版。

### 5.1 CLI 版现状

CLI 版目录：

```text
study_area/feishu/pi-feishu-bridge-cli/
```

CLI 版链路：

```text
收到飞书文本消息
  ↓
解析消息 text
  ↓
执行 PI_COMMAND -p "用户消息"
  ↓
捕获 stdout
  ↓
回复到飞书
```

CLI 版优点：简单，已经跑通飞书消息 → pi → 飞书回复。

CLI 版限制：

- 每条消息都会启动一次 pi CLI，有冷启动成本。
- 默认是单轮对话，不保留上下文。
- 不适合 `/abort`、任务状态、流式进度。
- 飞书重复推送时需要按 `message_id` 去重。

### 5.2 RPC 版目标

RPC 版目录：

```text
study_area/feishu/pi-feishu-bridge-rpc/
```

RPC 版目标链路：

```text
bridge 启动
  ↓
启动一个常驻 pi --mode rpc 子进程
  ↓
飞书消息到达
  ↓
bridge 通过 JSONL 向 pi RPC 发送 prompt
  ↓
bridge 从 pi RPC stdout 接收 response/event
  ↓
收集 assistant 最终文本
  ↓
回复到飞书
```

RPC 版建议模块：

```text
study_area/feishu/pi-feishu-bridge-rpc/
  README.md
  requirements.txt
  .env.example
  .gitignore

  src/
    main.py                 程序入口
    config.py               读取环境变量
    logging_config.py       日志配置

    feishu/
      client.py             创建飞书 OpenAPI client
      events.py             飞书事件解析
      messenger.py          回复飞书消息

    pi_rpc/
      process.py            启动和管理 pi --mode rpc 子进程
      protocol.py           JSONL 编解码、请求 ID、事件分发
      session.py            后续 session 管理

    app/
      bridge.py             核心流程：飞书消息 → RPC prompt → 飞书回复
      commands.py           /help /new /abort /status
```

RPC 版环境变量：

```bash
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
PI_COMMAND=/home/ringo/.nvm/versions/node/v22.22.2/bin/pi
PI_WORKDIR=/path/to/workdir
PI_SESSION_DIR=/path/to/sessions
PI_RPC_TIMEOUT_SECONDS=300
```

RPC 版第一步只做全局一个 RPC 进程、全局一个会话。多用户 session 隔离后续再做。

## 6. 第一阶段：CLI 最小可用原型

状态：已完成，目录为：

```text
study_area/feishu/pi-feishu-bridge-cli/
```

目标：飞书发一句，pi 回一句。

已完成：

1. bridge 入口启动飞书长连接事件消费者。
2. 使用 `APP_ID` / `APP_SECRET` 建立长连接。
3. 接收文本消息事件 `im.message.receive_v1`。
4. 调用本地 pi CLI：

   ```bash
   /home/ringo/.nvm/versions/node/v22.22.2/bin/pi -p "飞书用户消息"
   ```

5. 捕获 stdout。
6. 调用飞书 API 回复消息。
7. 按 `message_id` 做重复推送去重。
8. 加基本日志。

限制：

- 仍是单轮对话。
- 每条消息启动一次 pi CLI，延迟较高。
- 先不做流式。
- 先不做多轮 session。
- 先不处理附件。
- 先不让 pi 修改敏感目录。

## 7. 第二阶段：RPC、session 和命令

目标：用 RPC 版替代 CLI 版，让飞书会话能逐步对应 pi 会话。

设计：

```text
session key = tenant_key + chat_id + user_id
```

命令：

```text
/new       新建 pi 会话
/status    查看当前任务状态
/abort     中断当前任务
/help      显示帮助
```

需要解决：

- 同一个用户连续发消息时排队。
- pi 正在执行时，新消息如何处理。
- 错误回复如何简化展示。

## 8. 第三阶段：流式和长任务

目标：pi 执行中，飞书能看到进度。

策略：

- 任务开始时先回复：`已收到，开始执行...`
- 每隔 N 秒更新一次消息或追加一条进度消息。
- 完成后发送最终结果。
- 对长输出做截断，完整内容存成文件上传。

注意：飞书消息更新和频率限制需要单独处理，避免刷屏。

## 9. 第四阶段：Feishu CLI / 飞书工具接入

目标：让 pi 能主动使用飞书能力。

飞书现在有官方 Lark/Feishu CLI：

- npm 包：`@larksuite/cli`
- 命令：`lark-cli`
- GitHub：`larksuite/cli`
- 官方定位：给人和 AI Agent 使用的 Lark/Feishu CLI，覆盖 Messenger、Docs、Base、Sheets、Calendar、Mail、Tasks、Meetings 等领域。

官方快速安装方式：

```bash
npx @larksuite/cli@latest install
```

官方安装指南里的手动步骤：

```bash
npm install -g @larksuite/cli
npx -y skills add https://open.feishu.cn --skill -y
lark-cli config init --new
lark-cli auth login --recommend
lark-cli auth status
```

常用认证/配置命令：

```bash
lark-cli config init
lark-cli auth login
lark-cli auth status
lark-cli auth check
lark-cli auth logout
```

可以做成 pi extension tools：

```text
feishu_send_message
feishu_search_messages
feishu_get_doc
feishu_update_doc
feishu_upload_file
feishu_create_task
feishu_calendar_query
feishu_mail_search
```

优先实现方式：

```text
pi tool → child_process 调 lark-cli → 解析 JSON/stdout → 返回给 pi
```

后续再按需替换为 OpenAPI SDK 直连。

需要注意：

- Lark CLI 支持“应用身份”和“用户身份”两类能力；访问个人消息、日程、文档通常需要用户授权。
- 写操作必须默认要求确认。
- 明确区分只读 tool 和写入 tool。
- 避免让 pi 无限制读取飞书敏感内容。
- bridge 用飞书机器人处理“飞书里唤起 pi”；Lark CLI 用作“pi 主动操作飞书”的工具层，两者职责不同。

## 10. 安全边界

必须做：

- 校验飞书事件签名/token。
- 限制允许访问的飞书用户或群。
- bridge 只监听 localhost，公网通过 tunnel 转发。
- pi 工作目录使用专门目录，不要默认指向整个 home。
- 对危险命令加人工确认或禁用。
- 不把 `APP_SECRET`、飞书 token、pi auth 写入日志。

建议配置白名单：

```json
{
  "allowedUserIds": ["ou_xxx"],
  "allowedChatIds": ["oc_xxx"],
  "workspaceRoot": "/home/ringo/workspace/pi-feishu-workspace"
}
```

## 11. 验收标准

### 原型完成

- 飞书私聊机器人发送 `hello`。
- 本机 bridge 收到事件。
- 本地 pi 生成回答。
- 机器人把回答发回飞书。

### 可用版本完成

- 支持群聊 @ 机器人。
- 支持 `/new`、`/abort`、`/status`。
- 支持每个飞书用户独立 session。
- 支持长任务完成后回传摘要。
- 支持错误提示。

### 进阶版本完成

- pi 可以调用飞书工具。
- 支持飞书文档读取/写入。
- 支持附件下载和结果文件上传。
- 支持权限白名单和审计日志。

## 12. 推荐实施顺序

```text
1. 在飞书开放平台启用长连接事件接收
2. 跑通本机 bridge 长连接启动
3. 跑通接收文本消息 im.message.receive_v1
4. 跑通发送文本回复
5. bridge 调本地 pi CLI
6. 飞书消息 → pi → 飞书回复
7. 增加 session 映射
8. 增加命令系统
9. 调研 pi SDK/RPC，替换 CLI 调用
10. 增加 Feishu CLI/OpenAPI tools
11. 加权限、安全和日志
```

## 13. 关键待调研问题

- Node.js bridge 是直接用 `AgentSession`，还是先用 RPC 子进程。
- RPC 进程和飞书会话的映射策略：全局一个、每个 chat 一个、还是每个 user 一个。
- RPC `--session-dir` 是否按飞书会话隔离。
- extension UI request 如何映射到飞书消息卡片或普通文本确认。
- bridge 收到消息后，应该优先用 reply API 还是 send API。
- 飞书长连接 Node SDK 的事件 ACK、重连和错误处理机制。
- `lark-cli` 是否所有需要的命令都支持稳定 JSON 输出。
- `lark-cli` 的认证缓存位置、权限申请流程、user token / tenant token 切换方式。
- 飞书事件加密是否必须启用。

## 14. 已联网核实的信息

- 飞书机器人互动的核心链路是：事件订阅接收消息，服务端调用消息 API 回复。
- 接收消息事件为 `im.message.receive_v1`。
- 回复消息 API 为 `POST /open-apis/im/v1/messages/:message_id/reply`。
- 发送消息 API 为 `POST /open-apis/im/v1/messages`。
- 飞书官方文档建议本地开发用 `ngrok` 或 `localtunnel` 暴露 webhook。
- 官方 Lark/Feishu CLI 存在，npm 包是 `@larksuite/cli`，命令是 `lark-cli`。
- 官方 CLI 快速安装命令是 `npx @larksuite/cli@latest install`。
- 官方 CLI 支持 Messenger、Docs、Drive、Sheets、Base、Calendar、Meetings、Minutes、Email、Tasks、Wiki、Contacts 等能力。
- 旧的 `opdev` CLI 是开放平台开发工具，主要用于小程序/生态应用开发、预览、上传，不是本项目优先要接的 AI Agent 工具。

参考链接：

- https://open.feishu.cn/document/historical-version/interactive-session-based-robot/introduction?lang=zh-CN
- https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide
- https://open.larkoffice.com/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu.md
- https://github.com/larksuite/cli
- https://open.feishu.cn/document/no_class/feishu-developer-tool---command-line
