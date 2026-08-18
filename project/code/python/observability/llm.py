"""LLM 客户端工厂 + LangChain 回调埋点 + 就绪检查。"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI

from config import settings
from observability.metrics import record_llm_call

logger = logging.getLogger(__name__)


class LlmNotConfiguredError(RuntimeError):
    """OPENAI_API_KEY 未配置且 require_openai_api_key=True。"""


def ensure_llm_ready() -> None:
    """无 key 时快速失败，避免挂起下游调用。"""
    if not settings.require_openai_api_key:
        return
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("sk-your-api-key"):
        raise LlmNotConfiguredError(
            "OPENAI_API_KEY 未配置或仍为占位符。请在 .env 中设置有效密钥，"
            "或将 REQUIRE_OPENAI_API_KEY=false 仅用于本地无 LLM 调试。"
        )


def _usage_from_response(response: LLMResult) -> tuple[int, int]:
    prompt = completion = 0
    meta = response.llm_output or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    if prompt or completion:
        return prompt, completion
    for gens in response.generations or []:
        for gen in gens:
            msg = getattr(gen, "message", None)
            usage2 = getattr(msg, "usage_metadata", None) or {}
            if isinstance(usage2, dict):
                prompt += int(usage2.get("input_tokens") or 0)
                completion += int(usage2.get("output_tokens") or 0)
    return prompt, completion


class LlmMetricsHandler(BaseCallbackHandler):
    """记录 LLM 延迟 / token / 估算成本。"""

    def __init__(self, component: str = "llm") -> None:
        super().__init__()
        self.component = component
        self._starts: dict[UUID, float] = {}

    def on_chat_model_start(self, serialized: dict[str, Any], messages, *, run_id: UUID, **kwargs) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, **kwargs) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs) -> None:
        started = self._starts.pop(run_id, None)
        duration = (time.perf_counter() - started) if started is not None else 0.0
        prompt, completion = _usage_from_response(response)
        record_llm_call(
            self.component,
            duration,
            status="ok",
            prompt_tokens=prompt,
            completion_tokens=completion,
        )
        logger.info(
            "llm_call_ok component=%s duration_ms=%.2f prompt_tokens=%s completion_tokens=%s",
            self.component,
            duration * 1000,
            prompt,
            completion,
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> Any:
        started = self._starts.pop(run_id, None)
        duration = (time.perf_counter() - started) if started is not None else 0.0
        record_llm_call(self.component, duration, status="error")
        logger.exception(
            "llm_call_error component=%s duration_ms=%.2f",
            self.component,
            duration * 1000,
        )


def build_chat_openai(component: str = "llm", **overrides: Any) -> ChatOpenAI:
    """统一构造 ChatOpenAI：超时 / 有限重试 / 指标回调。

    密钥检查请在 API 入口调用 ensure_llm_ready()，避免测试/降级路径无法构造客户端。
    """
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key or "missing-key",
        "base_url": settings.openai_base_url,
        "temperature": 0,
        "timeout": settings.llm_request_timeout,
        "max_retries": max(0, int(settings.llm_max_retries)),
        "callbacks": [LlmMetricsHandler(component=component)],
    }
    kwargs.update(overrides)
    return ChatOpenAI(**kwargs)
