import logging
import logging.config
import os


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    is_json = str(json_format).lower() == "true"

    if is_json:
        fmt = (
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
            '"message":"%(message)s","module":"%(module)s","func":"%(funcName)s","line":"%(lineno)d","request_id":"%(request_id)s"}'
        )
    else:
        fmt = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s (request_id=%(request_id)s)"

    class RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "request_id"):
                record.request_id = "-"
            return True

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {"default": {"format": fmt}},
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                }
            },
            "root": {
                "handlers": ["default"],
                "level": level.upper(),
            },
        }
    )