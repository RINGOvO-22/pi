import lark_oapi as lark

from src.app.bridge import BridgeApp
from src.config import load_config
from src.feishu.client import create_openapi_client
from src.feishu.messenger import FeishuMessenger
from src.logging_config import setup_logging
from src.pi.runner import PiRunner


def main() -> None:
    setup_logging()
    config = load_config()

    openapi_client = create_openapi_client(config)
    messenger = FeishuMessenger(openapi_client)
    pi_runner = PiRunner(
        command=config.pi_command,
        workdir=config.pi_workdir,
        timeout_seconds=config.pi_timeout_seconds,
    )
    app = BridgeApp(messenger, pi_runner)

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(app.handle_message)
        .build()
    )

    ws_client = lark.ws.Client(
        config.feishu_app_id,
        config.feishu_app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    print("Starting pi-feishu-bridge-cli...")
    ws_client.start()


if __name__ == "__main__":
    main()
