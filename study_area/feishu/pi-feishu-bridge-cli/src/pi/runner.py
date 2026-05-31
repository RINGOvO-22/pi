import shlex
import subprocess
from pathlib import Path


class PiRunner:
    def __init__(self, command: str, workdir: Path, timeout_seconds: int) -> None:
        self.command = command
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds

    def run(self, prompt: str) -> str:
        self.workdir.mkdir(parents=True, exist_ok=True)
        args = [*shlex.split(self.command), "-p", prompt]

        result = subprocess.run(
            args,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                return f"pi 执行失败：\n{stderr}"
            return f"pi 执行失败，退出码：{result.returncode}"

        output = result.stdout.strip()
        if not output:
            return "pi 没有返回内容。"
        return output
