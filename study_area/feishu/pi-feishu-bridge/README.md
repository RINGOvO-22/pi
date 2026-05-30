# pi-feishu-bridge

最小 bridge：先只负责连接飞书长连接，并打印收到的消息事件。

## 1. 创建 conda 环境

推荐使用 conda 环境：

```bash
cd study_area/feishu/pi-feishu-bridge
conda create -n pi-feishu-bridge python=3.11 -y
conda activate pi-feishu-bridge
pip install -r requirements.txt
```

以后每次重新打开终端，只需要：

```bash
cd study_area/feishu/pi-feishu-bridge
conda activate pi-feishu-bridge
```

如果你想用更短的环境名，也可以把 `pi-feishu-bridge` 换成 `feishu-pi`。

## 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入飞书开放平台里的：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

第一版可以先不填：

```bash
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
```

## 3. 启动长连接

```bash
python bridge.py
```

看到类似日志后，保持这个进程运行：

```text
Starting Feishu long connection client...
Keep this process running, then click '验证连接状态' in Feishu Open Platform.
```

## 4. 回飞书后台验证

回到飞书开放平台的长连接配置页面，点击：

```text
验证连接状态
```

如果成功，说明本机 bridge 已经连上飞书。

## 5. 测试收消息

在飞书里私聊机器人，或在测试群里 @ 机器人。

如果配置正确，终端会打印 `im.message.receive_v1` 事件内容。
