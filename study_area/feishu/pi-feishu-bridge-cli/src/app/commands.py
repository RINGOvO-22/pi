HELP_TEXT = """支持的命令：
/help 显示帮助

第一版暂未支持 /new、/abort、/status。
""".strip()


def handle_command(text: str) -> str | None:
    command = text.strip()
    if command == "/help":
        return HELP_TEXT
    return None
