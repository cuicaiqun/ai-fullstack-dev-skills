"""P0-1：真实 Neo4j 双租户隔离 E2E。

默认跳过。本地/联调：

  bash scripts/e2e_tenant_neo4j.sh
"""

from __future__ import annotations

import os
import uuid

import pytest

from agents.knowledge_extract_agent import Entity, Relation
from services.knowledge_graph import KnowledgeGraphService

pytestmark = [pytest.mark.neo4j_e2e, pytest.mark.asyncio]


def _e2e_enabled() -> bool:
    return os.environ.get("RUN_NEO4J_E2E", "").strip().lower() in {"1", "true", "yes"}


@pytest.fixture
async def kg():
    if not _e2e_enabled():
        pytest.skip("set RUN_NEO4J_E2E=1 to run real Neo4j tenant E2E")
    service = KnowledgeGraphService()
    await service.init()
    if not service.is_connected:
        pytest.skip("Neo4j driver not connected")
    try:
        async with service._driver.session() as session:
            await session.run("RETURN 1 AS ok")
    except Exception as exc:
        await service.close()
        pytest.skip(f"Neo4j unavailable: {exc}")
    try:
        yield service
    finally:
        await service.close()


async def test_real_neo4j_dual_tenant_isolation(kg: KnowledgeGraphService):
    suffix = uuid.uuid4().hex[:8]
    org = f"E2E公司_{suffix}"
    person = f"E2E员工_{suffix}"
    t1, t2 = f"e2e-t1-{suffix}", f"e2e-t2-{suffix}"
    src1, src2 = f"/e2e/{suffix}/a.md", f"/e2e/{suffix}/b.md"

    await kg.upsert_entity(
        Entity(name=org, type="Organization", description="e2e-org"),
        source=src1,
        tenant_id=t1,
    )
    await kg.upsert_entity(
        Entity(name=person, type="Person", description="e2e-person"),
        source=src1,
        tenant_id=t1,
    )
    await kg.upsert_entity(
        Entity(name=org, type="Organization", description="e2e-org-t2"),
        source=src2,
        tenant_id=t2,
    )
    await kg.add_relation(
        Relation(head=person, relation="works_at", tail=org, confidence=0.95),
        source=src1,
        tenant_id=t1,
    )

    hits_t1 = await kg.search_entities(org, tenant_id=t1, limit=10)
    hits_t2 = await kg.search_entities(org, tenant_id=t2, limit=10)
    assert len([h for h in hits_t1 if h.get("name") == org]) >= 1
    assert len([h for h in hits_t2 if h.get("name") == org]) >= 1
    assert all(h.get("tenant_id") == t1 for h in hits_t1 if h.get("name") == org)
    assert all(h.get("tenant_id") == t2 for h in hits_t2 if h.get("name") == org)

    person_t2 = await kg.search_entities(person, tenant_id=t2, limit=10)
    assert person_t2 == []

    nbr = await kg.get_neighbors(person, tenant_id=t1, hops=1)
    assert any(row.get("target") == org for row in nbr)
    assert all(row.get("tenant_id") == t1 for row in nbr if row.get("tenant_id"))

    with pytest.raises(PermissionError):
        await kg.execute_cypher("MATCH (n) DETACH DELETE n", tenant_id=t1)
    with pytest.raises(PermissionError):
        await kg.execute_cypher("MATCH (n) RETURN n LIMIT 1", tenant_id=t1)

    await kg.delete_by_source(src1, tenant_id=t1)
    await kg.delete_by_source(src2, tenant_id=t2)
    assert await kg.search_entities(org, tenant_id=t1, limit=5) == []
    assert await kg.search_entities(org, tenant_id=t2, limit=5) == []
    assert await kg.search_entities(person, tenant_id=t1, limit=5) == []
