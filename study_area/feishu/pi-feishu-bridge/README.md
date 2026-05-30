# pi-feishu-bridge

正式 bridge 原型：接收飞书文本消息，调用本机 pi CLI，并把 pi 输出回复到飞书。

## 1. 安装依赖

可以复用已有 conda 环境：

```bash
cd study_area/feishu/pi-feishu-bridge
/home/ringo/miniforge3/envs/pi/bin/pip install -r requirements.txt
```

## 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
PI_COMMAND=/home/ringo/.nvm/versions/node/v22.22.2/bin/pi
PI_WORKDIR=/home/ringo/workspace/pi-feishu-workspace
PI_TIMEOUT_SECONDS=300
```

## 3. 启动

先单独确认 pi CLI 能返回：

```bash
cd /home/ringo/workspace/pi-feishu-workspace
/home/ringo/.nvm/versions/node/v22.22.2/bin/pi -p "只回复 OK"
```

再启动 bridge。bridge 项目目录下：

```bash
cd /home/ringo/workspace/pi/study_area/feishu/pi-feishu-bridge
/home/ringo/miniforge3/envs/pi/bin/python -m src.main
```

保持进程运行，然后在飞书里私聊机器人。

## 4. 当前能力

- 使用飞书长连接接收 `im.message.receive_v1`。
- 支持文本消息。
- 支持 `/help`。
- 调用本机 pi CLI：`PI_COMMAND -p "用户消息"`。
- 把 pi 的 stdout 作为唯一回复发回飞书。
- 按 `message_id` 跳过飞书重复推送的同一条消息。
- 长输出超过 4000 字符时截断。

## 5. 暂不支持

- 多轮 session。
- 流式回复。
- `/new`、`/abort`、`/status`。
- 文件和图片。
- 群聊复杂权限控制。
