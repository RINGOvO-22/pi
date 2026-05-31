import logging

import lark_oapi as lark

from src.app.commands import handle_command
from src.feishu.events import parse_text_message
from src.feishu.messenger import FeishuMessenger
from src.pi.runner import PiRunner

logger = logging.getLogger(__name__)

MAX_REPLY_CHARS = 4000


class BridgeApp:
    def __init__(self, messenger: FeishuMessenger, pi_runner: PiRunner) -> None:
        self.messenger = messenger
        self.pi_runner = pi_runner
        self.seen_message_ids: set[str] = set()

    def handle_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        event = parse_text_message(data)
        if event is None:
            logger.info("Skip non-text message")
            return

        if event.message_id in self.seen_message_ids:
            logger.info("Skip duplicate message message_id=%s", event.message_id)
            return
        self.seen_message_ids.add(event.message_id)

        logger.info(
            "Received text message message_id=%s chat_type=%s sender=%s",
            event.message_id,
            event.chat_type,
            event.sender_open_id,
        )

        command_reply = handle_command(event.text)
        if command_reply is not None:
            self.messenger.reply_text(event.message_id, command_reply)
            return

        reply = self.pi_runner.run(event.text)
        self.messenger.reply_text(event.message_id, self.format_reply(reply))

    def format_reply(self, reply: str) -> str:
        if len(reply) <= MAX_REPLY_CHARS:
            return reply
        return f"{reply[:MAX_REPLY_CHARS]}\n\n[输出过长，已截断]"
