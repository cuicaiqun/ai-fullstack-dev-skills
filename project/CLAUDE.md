# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Enterprise knowledge management system built as 4 collaborating agents orchestrated by LangGraph. It does multimodal document ingestion, GraphRAG (vector + knowledge-graph hybrid retrieval) question answering, and CDC-based incremental updates. The real code lives in `code/python/`. The `项目介绍/` directory is teaching/interview material (Chinese), not runnable code. Source comments and docstrings are in Chinese.

## Commands

All commands run from `code/`:

```bash
# Local stack (publish Neo4j/Chroma/Postgres ports; demo secrets allowed):
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file python/.env up

# Production-like (only API :8080; strong secrets required — see python/.env.production.example):
docker compose --env-file python/.env.production up

# Local dev without Docker — from code/python/
pip install -r requirements.txt
cp .env.example .env          # then fill in OPENAI_API_KEY etc.
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Tests (fixed entry — Python 3.11 preferred, per-test timeout 60s, wall 600s)
cd python && bash scripts/run_unit_tests.sh
bash scripts/run_unit_tests.sh tests/test_file.py::test_name   # single test
bash scripts/e2e_tenant_neo4j.sh                               # optional real Neo4j tenant E2E
# Or: PYTHON_BIN=/path/to/python3.11 bash scripts/run_unit_tests.sh
python scripts/check_p0_3_deploy.py     # P0-3 compose/secrets CI gate
```


Key ports: API `8080` (Swagger at `/docs`, web UI at `/`). With **dev overlay**: Neo4j UI `7474` / Bolt `7687`, ChromaDB `8000`, Kafka host `29092`. Production compose does **not** publish datastore ports.

## Architecture

Request → `api/main.py` (FastAPI) → `orchestrator/graph.py` (LangGraph) → agents → services → stores.

**Three compiled LangGraph pipelines**, built once in `build_knowledge_graph_workflow()` and stored in the module-level `workflows` dict during FastAPI `lifespan`:
- `ingest`: `parse` (DocParserAgent) → `extract` (KnowledgeExtractAgent) → `store_vectors` → `store_graph`
- `qa`: single `answer` node delegating to `QAAgent.answer()`
- `update`: `process` (KnowledgeUpdateAgent) → conditional `retry` for failed changes

Each pipeline uses a plain `dict` StateGraph; nodes return `{**state, ...}` merges.

**4 agents** (`agents/`), each wraps a `ChatOpenAI` client and is prompt-driven:
- `DocParserAgent` — classify → parse → chunk → metadata; emits `DocumentChunk` dataclasses
- `KnowledgeExtractAgent` — NER + relation extraction → `Entity`/`Relation` → `ExtractionResult`
- `QAAgent` — intent classify → query rewrite → parallel vector+graph retrieve → hybrid rerank → answer; returns `QAResult`
- `KnowledgeUpdateAgent` — consumes `DocumentChange` events, does diff/incremental re-index

**Services** (`services/`):
- `vector_store.py` — `VectorStoreService`, ChromaDB or PGVector backend (`VECTOR_STORE_TYPE`)
- `knowledge_graph.py` — `KnowledgeGraphService`, Neo4j; entities are `:Entity` nodes with `name`/`type`/`source`/`version`, indexed on init
- `graph_rag.py` — `GraphRAGPipeline`, the standalone hybrid retriever (vector + subgraph + shortest-path + community-summary), with cross-rerank weighting (path 1.25 > subgraph 1.15 > community 1.1 > vector 1.0)
- `cdc_processor.py`, `multimodal.py`, `embedding_worker.py`

LLM access is OpenAI-compatible throughout: every agent/service constructs `ChatOpenAI(model=settings.openai_model, base_url=settings.openai_base_url, ...)`. Point `OPENAI_BASE_URL` at any compatible endpoint (Qwen, Zhipu, Ollama, DeepSeek). Config is centralized in `config/settings.py` (pydantic-settings, loaded from `.env`); import via `from config import settings`.

## Critical non-obvious constraints

- **ChromaDB C-extension segfaults in async contexts.** `VectorStoreService.add_chunks`/`search`/`get_stats` deliberately **skip real ChromaDB calls** and track counts in memory (`_stored_count`) when the backend is `chroma`. This is a known workaround, not a bug — search returns `[]` under chroma. PGVector path does real queries. Don't "fix" these by re-adding direct chromadb calls in the event loop.
- **Embeddings run in a subprocess.** `embedding_worker.py` isolates PyTorch/sentence-transformers (`shibing624/text2vec-base-chinese`) in a separate process to keep segfaults from killing the server. `_SubprocessEmbeddings` is used only when `deepseek` is in the base URL; otherwise `OpenAIEmbeddings`.
- **`DISABLE_LOCAL_EMBEDDINGS=1`** forces LLM-only mode (no local embedding model) — check `embeddings_available` before storing/searching.
- **LLM JSON parsing is defensive.** Agents strip ```` ``` ```` fences and fall back to safe defaults on `JSONDecodeError`. Follow this pattern for any new LLM-JSON call.
- **Graceful degradation everywhere.** `lifespan` init and ingest/store nodes wrap store calls in bare `try/except` so the API stays up even if Neo4j/Chroma are down. Keep external-store failures non-fatal.
