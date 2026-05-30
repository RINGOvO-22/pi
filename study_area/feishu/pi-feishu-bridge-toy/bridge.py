import json
import os
import sys

from dotenv import load_dotenv
import lark_oapi as lark

FIXED_REPLY = "你好, 已接收到消息,暂未支持智能回复~"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def reply_text(client: lark.Client, message_id: str, text: str) -> None:
    request = (
        lark.im.v1.ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            lark.im.v1.ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        .build()
    )

    response = client.im.v1.message.reply(request)
    if not response.success():
        print(
            f"Failed to reply message: code={response.code}, msg={response.msg}, log_id={response.get_log_id()}",
            file=sys.stderr,
        )
        return

    print(f"Replied to message: {message_id}")


def on_message(client: lark.Client, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    print("Received im.message.receive_v1 event:")
    print(lark.JSON.marshal(data, indent=2))

    message = data.event.message
    if message.message_type != "text":
        print(f"Skip non-text message: {message.message_type}")
        return

    reply_text(client, message.message_id, FIXED_REPLY)


def main() -> None:
    load_dotenv()

    app_id = require_env("FEISHU_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET")

    openapi_client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.DEBUG)
        .build()
    )

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(lambda data: on_message(openapi_client, data))
        .build()
    )

    client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG,
    )

    print("Starting Feishu long connection client...")
    print("Keep this process running, then click '验证连接状态' in Feishu Open Platform.")
    client.start()


if __name__ == "__main__":
    main()
