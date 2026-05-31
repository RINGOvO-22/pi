import time

from src.config import load_config
from src.logging_config import setup_logging
from src.pi_rpc.process import PiRpcProcess


def main() -> None:
    setup_logging()
    config = load_config()

    rpc_process = PiRpcProcess(config)
    rpc_process.start()

    try:
        print(f"is_running: {rpc_process.is_running()}")
        print("stdin available:", rpc_process.stdin is not None)
        print("stdout available:", rpc_process.stdout is not None)
        print("Sleeping for 3 seconds, then stopping...")
        time.sleep(3)
    finally:
        rpc_process.stop()

    print(f"is_running after stop: {rpc_process.is_running()}")


if __name__ == "__main__":
    main()
