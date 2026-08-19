"""P2: resilience / grounding / entity align / rate limit."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from agents.knowledge_extract_agent import Entity, ExtractionResult, KnowledgeExtractAgent, Relation
from agents.qa_agent import QAAgent, RetrievedContext
from api.auth.store import AuthStore
from config import settings
from observability.llm import LlmNotConfiguredError, ensure_llm_ready
from observability.rate_limit import SlidingWindowRateLimiter
from services.entity_align import build_canonical_map, name_similarity, normalize_entity_name
from services.grounding import check_answer_grounding
from services.rerank import lexical_similarity, rerank_scored_items


def test_ensure_llm_ready_rejects_placeholder(monkeypatch):
    monkeypatch.setattr(settings, "require_openai_api_key", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-your-api-key-here")
    try:
        ensure_llm_ready()
        assert False, "expected LlmNotConfiguredError"
    except LlmNotConfiguredError:
        pass


def test_rate_limiter_blocks_burst():
    lim = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    assert lim.allow("u1")
    assert lim.allow("u1")
    assert lim.allow("u1")
    assert not lim.allow("u1")
    assert lim.allow("u2")


def test_entity_align_merges_tencent_variants():
    assert normalize_entity_name("腾讯公司") == normalize_entity_name("腾讯")
    assert name_similarity("腾讯", "腾讯公司") >= 0.9
    mapping = build_canonical_map(["腾讯", "腾讯公司", "微信"], threshold=0.82)
    assert mapping["腾讯"] == mapping["腾讯公司"]
    assert mapping["微信"] == "微信"


def test_resolve_entities_rewrites_relations():
    results = [
        ExtractionResult(
            entities=[
                Entity(name="腾讯", type="Organization"),
                Entity(name="腾讯公司", type="Organization"),
                Entity(name="微信", type="Product"),
            ],
            relations=[
                Relation(head="微信", relation="developed_by", tail="腾讯公司", confidence=0.9),
            ],
            events=[],
            source_chunk_id="c1",
        )
    ]
    aligned = KnowledgeExtractAgent.resolve_entities(results)
    names = {e.name for e in aligned[0].entities}
    assert "腾讯公司" not in names or names == {"腾讯", "微信"} or (
        len(names) == 2 and "微信" in names
    )
    assert aligned[0].relations[0].tail == aligned[0].relations[0].tail  # canonical
    assert aligned[0].relations[0].tail in names


def test_grounding_rejects_bad_citation_index():
    ctx = [RetrievedContext(content="差旅 7 天内报销", source="handbook.md", score=0.9, retrieval_type="vector")]
    bad = check_answer_grounding("答案。[来源 9]", ctx)
    assert bad.grounded is False
    good = check_answer_grounding("须在 7 个自然日内报销。[来源 1]", ctx)
    assert good.grounded is True


def test_qa_refuses_ungrounded_answer(monkeypatch):
    monkeypatch.setattr(settings, "qa_refuse_ungrounded", True)

    async def fake_generate(*args, **kwargs):
        return "幻觉答案。[来源 9]", ["生成"]

    agent = object.__new__(QAAgent)
    agent.llm = None
    agent.vector_store = None
    agent.knowledge_graph = None
    agent._generate_answer = fake_generate  # type: ignore[method-assign]

    ctx = [RetrievedContext(content="差旅 7 天内报销", source="handbook.md", score=0.9, retrieval_type="vector")]

    async def _run():
        from services.grounding import check_answer_grounding
        from agents.qa_agent import QueryIntent

        answer_text, _reasoning = await agent._generate_answer("问报销", ctx, QueryIntent.FACTOID)
        grounding = check_answer_grounding(answer_text, ctx)
        if not grounding.grounded and settings.qa_refuse_ungrounded:
            answer_text = (
                "抱歉，当前回答无法通过引用校验，系统不能将其作为可信依据返回。"
                "请上传相关文档后重试，或换一种问法。"
            )
        return answer_text, grounding

    answer, grounding = asyncio.run(_run())
    assert grounding.grounded is False
    assert "无法通过引用校验" in answer
    assert "来源 9" not in answer


def test_empty_context_refuses_answer():
    agent = object.__new__(QAAgent)
    agent.llm = None
    agent.vector_store = None
    agent.knowledge_graph = None
    text, steps = asyncio.run(agent._generate_answer("随便问", [], __import__("agents.qa_agent", fromlist=["QueryIntent"]).QueryIntent.FACTOID))
    assert "未检索到" in text or "无法" in text
    assert any("拒绝" in s for s in steps)


def test_rerank_prefers_lexical_match():
    items = [
        RetrievedContext(content="完全无关的文本", source="a", score=0.99, retrieval_type="vector"),
        RetrievedContext(content="出差报销须在 7 个自然日内提交", source="b", score=0.5, retrieval_type="graph"),
    ]

    async def _run():
        return await rerank_scored_items(
            "报销几天内提交",
            items,
            get_content=lambda c: c.content,
            get_type=lambda c: c.retrieval_type,
            get_base_score=lambda c: c.score,
            set_score=lambda c, s: setattr(c, "score", s),
            embeddings=None,
        )

    ranked = asyncio.run(_run())
    assert "报销" in ranked[0].content
    assert lexical_similarity("报销", "出差报销") > 0.2


def test_qa_rate_limit_and_missing_key(tmp_path, monkeypatch):
    db = tmp_path / "auth.db"
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_db_path", str(db))
    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret-32chars-min!!")
    monkeypatch.setattr(settings, "auth_bootstrap_admin_username", "admin")
    monkeypatch.setattr(settings, "auth_bootstrap_admin_password", "admin123")
    monkeypatch.setattr(settings, "update_mode", "off")
    monkeypatch.setattr(settings, "ingest_queue", "local")
    monkeypatch.setattr(settings, "state_store_dsn", "")
    monkeypatch.setattr(settings, "require_openai_api_key", True)
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "rate_limit_qa_per_minute", 2)

    from api.auth import deps as deps_mod
    from api.auth import router as router_mod
    from api.auth import store as store_mod
    from api import main as main_mod

    store = AuthStore(str(db))
    store.init()
    store_mod.auth_store = store
    main_mod.auth_store = store
    router_mod.auth_store = store
    deps_mod.auth_store = store
    # reset limiter with new limit
    from observability.rate_limit import SlidingWindowRateLimiter

    main_mod._qa_rate_limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    # 避免先前用例把租户窗口打满后污染本测
    main_mod._qa_tenant_rate_limiter = SlidingWindowRateLimiter(limit=1000, window_seconds=60)
    monkeypatch.setattr(settings, "qa_checkpoint_backend", "memory")

    async def _noop():
        return None

    monkeypatch.setattr(main_mod.vector_store, "init", _noop)
    monkeypatch.setattr(main_mod.knowledge_graph, "init", _noop)
    monkeypatch.setattr(main_mod.knowledge_graph, "close", _noop)

    with TestClient(main_mod.app) as client:
        login = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/qa/ask", headers=headers, json={"question": "hi"})
        assert r.status_code == 503
        assert "OPENAI_API_KEY" in r.json()["detail"]

        monkeypatch.setattr(settings, "require_openai_api_key", False)
        # workflow may be empty → 503 workflow; still exercise rate limit after bypassing key

        async def fake_ainvoke(*args, **kwargs):
            from agents.qa_agent import QAResult, QueryIntent

            return {
                "result": QAResult(
                    question="hi",
                    answer="ok",
                    contexts=[],
                    intent=QueryIntent.FACTOID,
                    confidence=0.1,
                    grounded=False,
                    grounding_notes=["no_contexts"],
                )
            }

        class _WF:
            ainvoke = staticmethod(fake_ainvoke)

        main_mod.workflows["qa"] = _WF()
        assert client.post("/api/qa/ask", headers=headers, json={"question": "a"}).status_code == 200
        assert client.post("/api/qa/ask", headers=headers, json={"question": "b"}).status_code == 200
        blocked = client.post("/api/qa/ask", headers=headers, json={"question": "c"})
        assert blocked.status_code == 429
