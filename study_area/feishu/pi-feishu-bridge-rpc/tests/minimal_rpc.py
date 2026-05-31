import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv


def read_json_line(stdout) -> dict:
    raw = stdout.readline()
    if raw == "":
        raise RuntimeError("pi RPC process exited before returning a JSON line")
    return json.loads(raw.rstrip("\n").rstrip("\r"))


def main() -> None:
    load_dotenv()

    pi_command = os.getenv("PI_COMMAND", "/home/ringo/.nvm/versions/node/v22.22.2/bin/pi")
    pi_workdir = Path(os.getenv("PI_WORKDIR", "/home/ringo/workspace/pi-feishu-workspace"))
    pi_session_dir = Path(os.getenv("PI_SESSION_DIR", "/home/ringo/workspace/pi-feishu-sessions"))
    prompt = sys.argv[1] if len(sys.argv) > 1 else "只回复 OK"

    pi_workdir.mkdir(parents=True, exist_ok=True)
    pi_session_dir.mkdir(parents=True, exist_ok=True)

    args = [
        pi_command,
        "--mode",
        "rpc",
        "--session-dir",
        str(pi_session_dir),
    ]

    print(f"Starting RPC process: {' '.join(args)}", file=sys.stderr)
    proc = subprocess.Popen(
        args,
        cwd=pi_workdir,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("failed to open pi RPC stdin/stdout")

    request_id = f"req-{uuid.uuid4()}"
    command = {"id": request_id, "type": "prompt", "message": prompt}

    proc.stdin.write(json.dumps(command, ensure_ascii=False) + "\n")
    proc.stdin.flush()

    text_parts: list[str] = []
    started_at = time.monotonic()
    timeout_seconds = 300

    try:
        while True:
            if time.monotonic() - started_at > timeout_seconds:
                raise TimeoutError(f"RPC prompt timed out after {timeout_seconds}s")

            event = read_json_line(proc.stdout)
            event_type = event.get("type")

            if event_type == "response" and event.get("id") == request_id:
                if not event.get("success"):
                    raise RuntimeError(f"prompt rejected: {event}")
                continue

            if event_type == "message_update":
                assistant_event = event.get("assistantMessageEvent", {})
                if assistant_event.get("type") == "text_delta":
                    delta = assistant_event.get("delta", "")
                    text_parts.append(delta)
                    print(delta, end="", flush=True)
                continue

            if event_type == "agent_end":
                print()
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    final_text = "".join(text_parts).strip()
    print("\n--- final text ---")
    print(final_text)


if __name__ == "__main__":
    main()
