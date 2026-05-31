HELP_TEXT = """支持的命令：
/help 显示帮助

RPC 第一版暂未接入 /new、/abort、/status。
""".strip()


def handle_command(text: str) -> str | None:
    command = text.strip()
    if command == "/help":
        return HELP_TEXT
    return None
