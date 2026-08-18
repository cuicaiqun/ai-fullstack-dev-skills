"""P0-1：Neo4j 租户隔离 — MERGE 键与只读门禁单测（无真实 Neo4j）。"""

from __future__ import annotations

import asyncio

import pytest

from agents.knowledge_extract_agent import Entity, Relation
from services.knowledge_graph import KnowledgeGraphService, resolve_tenant_id


class _Result:
    async def data(self):
        return []


class RecordingSession:
    def __init__(self):
        self.runs: list[tuple[str, dict]] = []

    async def run(self, cypher: str, params=None):
        self.runs.append((cypher, dict(params or {})))
        return _Result()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class RecordingDriver:
    def __init__(self):
        self.session_obj = RecordingSession()

    def session(self):
        return self.session_obj


def test_resolve_tenant_id_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(
        "services.knowledge_graph.settings.auth_bootstrap_tenant_id", "default-tenant"
    )
    assert resolve_tenant_id(None) == "default-tenant"
    assert resolve_tenant_id("  ") == "default-tenant"
    assert resolve_tenant_id("acme") == "acme"


def test_upsert_entity_merges_on_tenant_and_name():
    kg = KnowledgeGraphService()
    driver = RecordingDriver()
    kg._driver = driver

    ent = Entity(name="腾讯", type="Organization", description="公司")
    asyncio.run(kg.upsert_entity(ent, source="doc-a", tenant_id="t1"))
    asyncio.run(kg.upsert_entity(ent, source="doc-b", tenant_id="t2"))

    runs = driver.session_obj.runs
    assert len(runs) == 2
    for cypher, params in runs:
        assert "MERGE (e:Entity {tenant_id: $tenant_id, name: $name})" in cypher
    assert runs[0][1]["tenant_id"] == "t1"
    assert runs[1][1]["tenant_id"] == "t2"
    assert runs[0][1]["name"] == runs[1][1]["name"] == "腾讯"


def test_add_relation_matches_same_tenant_only():
    kg = KnowledgeGraphService()
    driver = RecordingDriver()
    kg._driver = driver
    rel = Relation(head="A", relation="related_to", tail="B", confidence=0.9)
    asyncio.run(kg.add_relation(rel, tenant_id="tenant-x"))
    cypher, params = driver.session_obj.runs[0]
    assert "tenant_id: $tenant_id" in cypher
    assert params["tenant_id"] == "tenant-x"


def test_execute_cypher_blocks_writes_and_unscoped_reads():
    kg = KnowledgeGraphService()
    driver = RecordingDriver()
    kg._driver = driver

    with pytest.raises(PermissionError):
        asyncio.run(kg.execute_cypher("MATCH (n) DELETE n", tenant_id="t1"))

    with pytest.raises(PermissionError):
        asyncio.run(
            kg.execute_cypher(
                "MATCH (e:Entity {name: $name}) RETURN e",
                {"name": "x"},
                tenant_id="t1",
            )
        )


def test_neighbors_and_search_inject_tenant():
    kg = KnowledgeGraphService()
    driver = RecordingDriver()
    kg._driver = driver

    asyncio.run(kg.get_neighbors("腾讯", tenant_id="tenant-a"))
    asyncio.run(kg.search_entities("腾讯", tenant_id="tenant-a"))
    asyncio.run(kg.shortest_paths("A", "B", tenant_id="tenant-a"))

    for cypher, params in driver.session_obj.runs:
        assert "$tenant_id" in cypher
        assert params["tenant_id"] == "tenant-a"
        assert "tenant_id" in cypher


def test_delete_by_source_scoped_to_tenant():
    kg = KnowledgeGraphService()
    driver = RecordingDriver()
    kg._driver = driver
    asyncio.run(kg.delete_by_source("/data/a.md", tenant_id="tenant-z"))
    cypher, params = driver.session_obj.runs[0]
    assert "tenant_id: $tenant_id" in cypher
    assert params["tenant_id"] == "tenant-z"
    assert params["source"] == "/data/a.md"
