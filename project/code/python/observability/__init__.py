"""可观测性：结构化日志、请求 ID、Prometheus、LLM 埋点。"""

from .logging_config import setup_logging
from .metrics import observe_http, record_llm_call

__all__ = [
    "setup_logging",
    "observe_http",
    "record_llm_call",
]
