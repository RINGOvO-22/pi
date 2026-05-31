import lark_oapi as lark

from src.config import Config


def create_openapi_client(config: Config) -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(config.feishu_app_id)
        .app_secret(config.feishu_app_secret)
        .log_level(lark.LogLevel.INFO)
        .build()
    )
