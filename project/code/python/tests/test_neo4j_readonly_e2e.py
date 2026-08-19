"""P0-5：Neo4j 只读账户 E2E。

默认跳过。先创建只读用户：

  NEO4J_PASSWORD=password bash scripts/create_neo4j_readonly_user.sh

再跑：

  RUN_NEO4J_READONLY_E2E=1 NEO4J_READ_USER=readonly NEO4J_READ_PASSWORD=... \\
    bash scripts/run_unit_tests.sh tests/test_neo4j_readonly_e2e.py -vv
"""

from __future__ import annotations

import os
import uuid

import pytest
from neo4j import READ_ACCESS, AsyncGraphDatabase

from agents.knowledge_extract_agent import Entity
from config import settings
from services.knowledge_graph import KnowledgeGraphService

pytestmark = [pytest.mark.neo4j_readonly_e2e, pytest.mark.asyncio]


def _enabled() -> bool:
    return os.environ.get("RUN_NEO4J_READONLY_E2E", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@pytest.fixture
async def kg_with_readonly():
    if not _enabled():
        pytest.skip("set RUN_NEO4J_READONLY_E2E=1")
    read_user = (os.environ.get("NEO4J_READ_USER") or settings.neo4j_read_user or "").strip()
    read_pass = os.environ.get("NEO4J_READ_PASSWORD") or settings.neo4j_read_password or ""
    if not read_user or not read_pass:
        pytest.skip("NEO4J_READ_USER/PASSWORD required")

    # apply to settings for KnowledgeGraphService.init
    settings.neo4j_read_user = read_user
    settings.neo4j_read_password = read_pass

    kg = KnowledgeGraphService()
    await kg.init()
    assert kg._read_driver is not None
    try:
        yield kg, read_user, read_pass
    finally:
        await kg.close()


async def test_readonly_user_cannot_write(kg_with_readonly):
    kg, read_user, read_pass = kg_with_readonly
    suffix = uuid.uuid4().hex[:8]
    name = f"RO_DENY_{suffix}"

    # write via admin path succeeds
    await kg.upsert_entity(
        Entity(name=name, type="Concept", description="readonly-e2e"),
        source=f"/e2e/ro-{suffix}.md",
        tenant_id=f"ro-{suffix}",
    )
    hits = await kg.search_entities(name, tenant_id=f"ro-{suffix}")
    assert any(h.get("name") == name for h in hits)

    # direct readonly driver write must fail
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(read_user, read_pass)
    )
    try:
        async with driver.session(default_access_mode=READ_ACCESS) as session:
            with pytest.raises(Exception):
                result = await session.run(
                    "CREATE (n:Entity {tenant_id: $t, name: $n}) RETURN n",
                    {"t": f"ro-{suffix}", "n": f"hack_{suffix}"},
                )
                await result.data()
    finally:
        await driver.close()

    # cleanup with write driver
    await kg.delete_by_source(f"/e2e/ro-{suffix}.md", tenant_id=f"ro-{suffix}")


async def test_readonly_search_via_service(kg_with_readonly):
    kg, _, _ = kg_with_readonly
    suffix = uuid.uuid4().hex[:8]
    name = f"RO_OK_{suffix}"
    tenant = f"ro-{suffix}"
    source = f"/e2e/ro-ok-{suffix}.md"
    await kg.upsert_entity(
        Entity(name=name, type="Concept", description="readable"),
        source=source,
        tenant_id=tenant,
    )
    hits = await kg.search_entities(name, tenant_id=tenant)
    assert any(h.get("name") == name for h in hits)
    await kg.delete_by_source(source, tenant_id=tenant)
