import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    feishu_app_id: str
    feishu_app_secret: str
    pi_command: str
    pi_workdir: Path
    pi_timeout_seconds: int


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def load_config() -> Config:
    load_dotenv()

    return Config(
        feishu_app_id=require_env("FEISHU_APP_ID"),
        feishu_app_secret=require_env("FEISHU_APP_SECRET"),
        pi_command=require_env("PI_COMMAND"),
        pi_workdir=Path(require_env("PI_WORKDIR")),
        pi_timeout_seconds=int(os.getenv("PI_TIMEOUT_SECONDS", "300")),
    )
