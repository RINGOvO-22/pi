import json
from dataclasses import dataclass

import lark_oapi as lark


@dataclass(frozen=True)
class TextMessageEvent:
    message_id: str
    chat_id: str
    chat_type: str
    sender_open_id: str
    text: str


def parse_text_message(data: lark.im.v1.P2ImMessageReceiveV1) -> TextMessageEvent | None:
    message = data.event.message
    if message.message_type != "text":
        return None

    content = json.loads(message.content)
    text = content.get("text", "")
    for mention in message.mentions or []:
        text = text.replace(mention.key, "")
    text = text.strip()
    sender_open_id = data.event.sender.sender_id.open_id

    return TextMessageEvent(
        message_id=message.message_id,
        chat_id=message.chat_id,
        chat_type=message.chat_type,
        sender_open_id=sender_open_id,
        text=text,
    )
