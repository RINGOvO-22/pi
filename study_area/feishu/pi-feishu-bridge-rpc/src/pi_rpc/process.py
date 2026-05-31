import logging
import subprocess
import threading
from pathlib import Path
from types import TracebackType

from src.config import Config

logger = logging.getLogger(__name__)


class PiRpcProcess:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self.stderr_thread: threading.Thread | None = None

    @property
    def stdin(self):
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("pi RPC process is not started")
        return self.process.stdin

    @property
    def stdout(self):
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("pi RPC process is not started")
        return self.process.stdout

    def command_args(self) -> list[str]:
        return [
            self.config.pi_command,
            "--mode",
            "rpc",
            "--session-dir",
            str(self.config.pi_session_dir),
        ]

    def start(self) -> None:
        if self.is_running():
            logger.info("pi RPC process is already running")
            return

        self.config.pi_workdir.mkdir(parents=True, exist_ok=True)
        self.config.pi_session_dir.mkdir(parents=True, exist_ok=True)

        args = self.command_args()
        logger.info("Starting pi RPC process: %s", " ".join(args))
        logger.info("pi RPC working directory: %s", self.config.pi_workdir)

        self.process = subprocess.Popen(
            args,
            cwd=self.config.pi_workdir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self.stderr_thread = threading.Thread(
            target=self._log_stderr,
            name="pi-rpc-stderr",
            daemon=True,
        )
        self.stderr_thread.start()

    def stop(self) -> None:
        if self.process is None:
            return

        if self.process.poll() is not None:
            logger.info("pi RPC process already exited with code %s", self.process.returncode)
            self.process = None
            return

        logger.info("Stopping pi RPC process")
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("pi RPC process did not exit after terminate; killing")
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            self.process = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def returncode(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()

    def _log_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return

        for line in process.stderr:
            logger.warning("pi RPC stderr: %s", line.rstrip("\n").rstrip("\r"))

    def __enter__(self) -> "PiRpcProcess":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()
