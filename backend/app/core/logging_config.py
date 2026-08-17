"""
结构化日志配置 —— 使用 Python logging + JSON 格式输出
替代全项目中的 print() 调用，支持时间、级别、链路追踪。
"""
import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """输出 JSON 格式的结构化日志"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 合并 extra 字段
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_entry.update(record.extra_fields)

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class GlintLogger(logging.LoggerAdapter):
    """带结构化 extra 字段的 Logger 适配器"""

    def process(self, msg, kwargs):
        extra_fields = kwargs.pop("extra", {})
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


def setup_logging(level: str = "INFO") -> None:
    """初始化结构化日志，替换 root logger 的 handler"""
    root_logger = logging.getLogger()
    # 清除已有 handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 降低第三方库日志噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
