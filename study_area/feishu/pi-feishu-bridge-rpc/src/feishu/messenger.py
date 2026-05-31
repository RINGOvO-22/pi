import json
import logging
import sys

import lark_oapi as lark

logger = logging.getLogger(__name__)


class FeishuMessenger:
    def __init__(self, client: lark.Client) -> None:
        self.client = client

    def reply_text(self, message_id: str, text: str) -> bool:
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

        response = self.client.im.v1.message.reply(request)
        if not response.success():
            print(
                f"Failed to reply message: code={response.code}, msg={response.msg}, log_id={response.get_log_id()}",
                file=sys.stderr,
            )
            return False

        logger.info("Replied to message %s", message_id)
        return True
