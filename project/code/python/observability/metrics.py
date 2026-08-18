"""Prometheus 指标与 LLM/HTTP 观测辅助。"""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    generate_latest,
)

# 独立 registry，便于测试隔离
REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    registry=REGISTRY,
)
LLM_REQUESTS = Counter(
    "llm_requests_total",
    "LLM calls",
    ["component", "status"],
    registry=REGISTRY,
)
LLM_LATENCY = Histogram(
    "llm_request_duration_seconds",
    "LLM call latency",
    ["component"],
    registry=REGISTRY,
)
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "LLM tokens (prompt/completion)",
    ["component", "direction"],
    registry=REGISTRY,
)
LLM_COST_USD = Counter(
    "llm_estimated_cost_usd_total",
    "Estimated LLM cost in USD (rough heuristic)",
    ["component"],
    registry=REGISTRY,
)
PIPELINE_EVENTS = Counter(
    "pipeline_events_total",
    "Ingest/update pipeline events",
    ["pipeline", "stage", "status"],
    registry=REGISTRY,
)
DEP_UP = Gauge(
    "dependency_up",
    "Dependency readiness (1=up, 0=down)",
    ["name"],
    registry=REGISTRY,
)

# 粗略成本估算（USD / 1K tokens）；无精确价时作可观测占位
_PROMPT_COST_PER_1K = 0.0005
_COMPLETION_COST_PER_1K = 0.0015


def observe_http(method: str, path: str, status: int, duration_sec: float) -> None:
    # 归一化路径，避免高基数
    norm = _normalize_path(path)
    HTTP_REQUESTS.labels(method=method, path=norm, status=str(status)).inc()
    HTTP_LATENCY.labels(method=method, path=norm).observe(duration_sec)


def record_llm_call(
    component: str,
    duration_sec: float,
    *,
    status: str = "ok",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    LLM_REQUESTS.labels(component=component, status=status).inc()
    LLM_LATENCY.labels(component=component).observe(duration_sec)
    if prompt_tokens:
        LLM_TOKENS.labels(component=component, direction="prompt").inc(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS.labels(component=component, direction="completion").inc(completion_tokens)
    cost = (
        prompt_tokens / 1000.0 * _PROMPT_COST_PER_1K
        + completion_tokens / 1000.0 * _COMPLETION_COST_PER_1K
    )
    if cost:
        LLM_COST_USD.labels(component=component).inc(cost)


def record_pipeline(pipeline: str, stage: str, status: str) -> None:
    PIPELINE_EVENTS.labels(pipeline=pipeline, stage=stage, status=status).inc()


def set_dependency_up(name: str, up: bool) -> None:
    DEP_UP.labels(name=name).set(1 if up else 0)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    # 保留前两段，避免 doc_id / filename 爆炸
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "/"
    if parts[0] == "api" and len(parts) >= 2:
        return "/" + "/".join(parts[:3]) if len(parts) >= 3 else "/" + "/".join(parts)
    return "/" + parts[0]


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def seconds(self) -> float:
        return time.perf_counter() - self._start
