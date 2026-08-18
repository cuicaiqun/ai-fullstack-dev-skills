"""P1-4 observability: request id, metrics, silent-exception logging."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.messages import AIMessage

from observability.context import get_request_id
from observability.llm import LlmMetricsHandler
from observability.logging_config import setup_logging
from observability.metrics import LLM_REQUESTS, metrics_payload, record_pipeline
from observability.middleware import RequestContextMiddleware
from orchestrator.graph import _build_ingest_graph


def test_request_id_middleware_sets_header_and_context():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping():
        return {"rid": get_request_id()}

    client = TestClient(app)
    resp = client.get("/ping", headers={"X-Request-ID": "req-fixed-001"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "req-fixed-001"
    assert resp.json()["rid"] == "req-fixed-001"


def test_metrics_payload_contains_http_and_pipeline_series():
    record_pipeline("ingest", "store_vectors", "ok")
    body, content_type = metrics_payload()
    text = body.decode("utf-8")
    assert "text/plain" in content_type or "openmetrics" in content_type or "prometheus" in content_type.lower() or content_type.startswith("text/")
    assert "pipeline_events_total" in text
    assert "http_requests_total" in text or "pipeline_events_total" in text


def test_llm_metrics_handler_records_success():
    before = LLM_REQUESTS.labels(component="test_comp", status="ok")._value.get()
    handler = LlmMetricsHandler(component="test_comp")
    run_id = __import__("uuid").uuid4()
    handler.on_chat_model_start({}, [], run_id=run_id)
    result = LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="hi"))]],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    )
    handler.on_llm_end(result, run_id=run_id)
    after = LLM_REQUESTS.labels(component="test_comp", status="ok")._value.get()
    assert after >= before + 1


def test_store_vectors_logs_on_failure(capsys):
    setup_logging("INFO")
    vs = MagicMock()
    vs.embeddings_available = True
    vs.add_chunks = AsyncMock(side_effect=RuntimeError("chroma down"))

    chunk = MagicMock()
    chunk.doc_id = "d1"
    doc_parser = MagicMock()
    doc_parser.parse_batch = AsyncMock(return_value=[chunk])
    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=[])

    graph = _build_ingest_graph(
        doc_parser=doc_parser,
        extractor=extractor,
        vector_store=vs,
        knowledge_graph=None,
    )

    import asyncio

    out = asyncio.run(graph.ainvoke({"file_paths": ["/tmp/a.md"]}))
    assert out.get("vectors_stored", 0) == 0
    assert out.get("vectors_ok") is False
    assert out.get("store_ok") is False
    logged = capsys.readouterr().out
    assert "store_vectors failed" in logged
    assert "chroma down" in logged
