"""
知识图谱服务 — Neo4j 图数据库操作（租户隔离）

P0-1：实体唯一键为 (tenant_id, name)；读写默认强制 tenant 谓词。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from agents.knowledge_extract_agent import Entity, Relation
from config import settings

logger = logging.getLogger(__name__)

_WRITE_CYPHER = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL\s+\w+\.|\bFOREACH)\b",
    re.IGNORECASE,
)


def resolve_tenant_id(tenant_id: str | None = None) -> str:
    tid = (tenant_id or "").strip()
    return tid or settings.auth_bootstrap_tenant_id or "default"


class KnowledgeGraphService:
    """Neo4j 知识图谱服务（tenant 分区）

    P0-5：写路径使用 NEO4J_USER；读路径优先 NEO4J_READ_USER（只读角色）。
    """

    def __init__(self) -> None:
        self._write_driver: Any = None
        self._read_driver: Any = None
        self._doc_search_gate: Any = None

    def set_doc_searchable_checker(self, checker: Any) -> None:
        """Inject state_store.document_search_gate for P0-2 graph retrieval."""
        self._doc_search_gate = checker

    def _row_searchable(self, *refs: str) -> bool:
        if not self._doc_search_gate:
            return True
        saw_deny = False
        saw_allow = False
        for ref in refs:
            value = str(ref or "").strip()
            if not value:
                continue
            try:
                gate = self._doc_search_gate(value)
            except Exception:
                logger.exception("graph search gate failed for %s", value)
                return False
            if gate is False or gate == "deny":
                saw_deny = True
            elif gate is True or gate == "allow":
                saw_allow = True
        if saw_deny:
            return False
        return True

    def _filter_searchable(self, rows: list[dict]) -> list[dict]:
        """Drop graph hits whose source/doc is pending or failed (P0-2).

        Neighbor rows use start_source/neighbor_source (paths), not ``source``
        which is the entity *name* in get_neighbors results.
        """
        if not self._doc_search_gate:
            return rows
        kept: list[dict] = []
        for row in rows:
            if "node_sources" in row:
                refs = list(row.get("node_sources") or [])
            elif "start_source" in row or "neighbor_source" in row:
                refs = [row.get("start_source"), row.get("neighbor_source")]
            else:
                refs = [row.get("source"), row.get("doc_id")]
            if self._row_searchable(*[str(x or "") for x in refs]):
                kept.append(row)
        return kept

    @property
    def _driver(self) -> Any:
        """兼容旧测试对 ``_driver`` 的注入。"""
        return self._write_driver

    @_driver.setter
    def _driver(self, value: Any) -> None:
        self._write_driver = value
        # 单测注入时读写共用同一 fake driver
        if self._read_driver is None:
            self._read_driver = value

    def _driver_for(self, *, write: bool = False) -> Any:
        if write:
            return self._write_driver
        return self._read_driver or self._write_driver

    # 单测兼容：旧字段名指向写驱动
    @property
    def _driver(self) -> Any:
        return self._write_driver

    @_driver.setter
    def _driver(self, value: Any) -> None:
        self._write_driver = value

    async def init(self) -> None:
        from neo4j import AsyncGraphDatabase

        self._write_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        read_user = (settings.neo4j_read_user or "").strip()
        if read_user:
            self._read_driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(read_user, settings.neo4j_read_password or ""),
            )
            logger.info("Neo4j read driver enabled user=%s", read_user)
        else:
            self._read_driver = None
            logger.info("Neo4j read driver falls back to write user")
        await self._ensure_indexes()

    async def close(self) -> None:
        for drv in (self._read_driver, self._write_driver):
            if drv is not None:
                try:
                    await drv.close()
                except Exception:
                    logger.exception("neo4j driver close failed")
        self._read_driver = None
        self._write_driver = None

    async def _ensure_indexes(self) -> None:
        index_queries = [
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.type)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.source)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.tenant_id)",
            # Neo4j 5 composite uniqueness — 失败则降级为普通索引（兼容旧库）
            "CREATE CONSTRAINT entity_tenant_name IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.tenant_id, e.name) IS NODE KEY",
        ]
        async with self._write_driver.session() as session:
            for q in index_queries:
                try:
                    await session.run(q)
                except Exception:
                    logger.warning("index/constraint skipped: %s", q[:80])
                    # 部分版本不支持 NODE KEY，尝试 UNIQUE
                    if "NODE KEY" in q:
                        try:
                            await session.run(
                                "CREATE CONSTRAINT entity_tenant_name IF NOT EXISTS "
                                "FOR (e:Entity) REQUIRE (e.tenant_id, e.name) IS UNIQUE"
                            )
                        except Exception:
                            logger.warning("unique constraint on (tenant_id,name) unavailable")

    @property
    def is_connected(self) -> bool:
        return self._write_driver is not None

    # ── entity operations ────────────────────────────────────

    async def upsert_entity(
        self,
        entity: Entity,
        version: int = 1,
        source: str = "",
        tenant_id: str | None = None,
    ) -> None:
        if not self._driver_for(write=True):
            return
        tid = resolve_tenant_id(tenant_id)
        cypher = """
        MERGE (e:Entity {tenant_id: $tenant_id, name: $name})
        ON CREATE SET
            e.type = $type,
            e.description = $description,
            e.version = $version,
            e.source = $source,
            e.created_at = $now,
            e.updated_at = $now
        ON MATCH SET
            e.type = CASE WHEN $type <> '' THEN $type ELSE e.type END,
            e.description = CASE WHEN $description <> '' THEN $description ELSE e.description END,
            e.version = $version,
            e.source = CASE WHEN $source <> '' THEN $source ELSE e.source END,
            e.updated_at = $now
        """
        async with self._driver_for(write=True).session() as session:
            await session.run(
                cypher,
                {
                    "tenant_id": tid,
                    "name": entity.name,
                    "type": entity.type,
                    "description": entity.description,
                    "version": version,
                    "source": source,
                    "now": int(time.time()),
                },
            )

    async def add_relation(
        self,
        relation: Relation,
        source: str = "",
        tenant_id: str | None = None,
    ) -> None:
        if not self._driver_for(write=True):
            return
        tid = resolve_tenant_id(tenant_id)
        rel_type = relation.relation.upper().replace(" ", "_")
        # 仅连接同租户实体，关系上也打 tenant_id 便于排查
        cypher = f"""
        MATCH (h:Entity {{tenant_id: $tenant_id, name: $head}})
        MATCH (t:Entity {{tenant_id: $tenant_id, name: $tail}})
        MERGE (h)-[r:{rel_type} {{tenant_id: $tenant_id}}]->(t)
        SET r.confidence = $confidence, r.source = $source, r.updated_at = $now
        """
        async with self._driver_for(write=True).session() as session:
            await session.run(
                cypher,
                {
                    "tenant_id": tid,
                    "head": relation.head,
                    "tail": relation.tail,
                    "confidence": relation.confidence,
                    "source": source,
                    "now": int(time.time()),
                },
            )

    # ── query operations ─────────────────────────────────────

    async def execute_cypher(
        self,
        cypher: str,
        params: dict | None = None,
        *,
        tenant_id: str | None = None,
        allow_write: bool = False,
        require_tenant: bool = True,
    ) -> list[dict]:
        """
        执行 Cypher。默认只读且要求租户上下文（P0-1/P0-5 防护薄层）。
        自由 LLM Cypher 不应再调用本方法写库；QA 请用 search/get_neighbors/shortest_paths。
        """
        driver = self._driver_for(write=allow_write)
        if not driver:
            return []
        if not allow_write and _WRITE_CYPHER.search(cypher or ""):
            logger.warning("blocked write cypher: %s", (cypher or "")[:120])
            raise PermissionError("Write Cypher is not allowed on this API")
        params = dict(params or {})
        if require_tenant:
            tid = resolve_tenant_id(tenant_id or params.get("tenant_id"))
            params["tenant_id"] = tid
            # 粗检：查询文本应引用 $tenant_id（参数化检索工具保证）；否则拒绝
            if "$tenant_id" not in (cypher or "") and "tenant_id" not in (cypher or ""):
                logger.warning("cypher missing tenant predicate rejected")
                raise PermissionError("Cypher must be scoped by tenant_id")
        async with driver.session() as session:
            result = await session.run(cypher, params)
            return await result.data()

    async def get_entity(self, name: str, tenant_id: str | None = None) -> dict | None:
        tid = resolve_tenant_id(tenant_id)
        cypher = """
        MATCH (e:Entity {tenant_id: $tenant_id, name: $name})
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.tenant_id AS tenant_id, e.source AS source
        """
        records = await self.execute_cypher(
            cypher, {"name": name, "tenant_id": tid}, tenant_id=tid, require_tenant=True
        )
        filtered = self._filter_searchable(records)
        return filtered[0] if filtered else None

    async def get_neighbors(
        self,
        entity_name: str,
        hops: int = 2,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        tid = resolve_tenant_id(tenant_id)
        hops = max(1, min(int(hops), 3))
        cypher = f"""
        MATCH path = (start:Entity {{tenant_id: $tenant_id, name: $name}})-[*1..{hops}]-(neighbor:Entity)
        WHERE neighbor.tenant_id = $tenant_id
        RETURN
            start.name AS source,
            [r IN relationships(path) | type(r)] AS relations,
            neighbor.name AS target,
            neighbor.type AS target_type,
            neighbor.description AS target_desc,
            start.tenant_id AS tenant_id,
            start.source AS start_source,
            neighbor.source AS neighbor_source
        LIMIT $limit
        """
        rows = await self.execute_cypher(
            cypher,
            {"name": entity_name, "tenant_id": tid, "limit": limit},
            tenant_id=tid,
        )
        return self._filter_searchable(rows)

    async def shortest_paths(
        self,
        name_a: str,
        name_b: str,
        tenant_id: str | None = None,
        max_hops: int = 5,
        limit: int = 3,
    ) -> list[dict]:
        tid = resolve_tenant_id(tenant_id)
        max_hops = max(1, min(int(max_hops), 5))
        cypher = f"""
        MATCH path = shortestPath(
            (a:Entity {{tenant_id: $tenant_id, name: $name_a}})-[*..{max_hops}]-
            (b:Entity {{tenant_id: $tenant_id, name: $name_b}})
        )
        WHERE all(n IN nodes(path) WHERE n.tenant_id = $tenant_id)
        RETURN
            [n IN nodes(path) | n.name] AS node_names,
            [r IN relationships(path) | type(r)] AS rel_types,
            [n IN nodes(path) | coalesce(n.source, '')] AS node_sources
        LIMIT $limit
        """
        rows = await self.execute_cypher(
            cypher,
            {
                "tenant_id": tid,
                "name_a": name_a,
                "name_b": name_b,
                "limit": limit,
            },
            tenant_id=tid,
        )
        return self._filter_searchable(rows)

    async def search_entities(
        self,
        keyword: str,
        limit: int = 20,
        tenant_id: str | None = None,
    ) -> list[dict]:
        tid = resolve_tenant_id(tenant_id)
        cypher = """
        MATCH (e:Entity {tenant_id: $tenant_id})
        WHERE e.name CONTAINS $keyword OR coalesce(e.description, '') CONTAINS $keyword
        RETURN e.name AS name, e.type AS type, e.description AS description,
               e.tenant_id AS tenant_id, e.source AS source
        LIMIT $limit
        """
        rows = await self.execute_cypher(
            cypher,
            {"keyword": keyword, "limit": limit, "tenant_id": tid},
            tenant_id=tid,
        )
        return self._filter_searchable(rows)

    async def delete_by_source(self, source: str, tenant_id: str | None = None) -> int:
        tid = resolve_tenant_id(tenant_id)
        cypher = """
        MATCH (e:Entity {source: $source, tenant_id: $tenant_id})
        DETACH DELETE e
        RETURN count(e) AS deleted
        """
        # allow_write for internal maintenance
        if not self._driver_for(write=True):
            raise RuntimeError("knowledge graph not connected")
        async with self._driver_for(write=True).session() as session:
            result = await session.run(cypher, {"source": source, "tenant_id": tid})
            records = await result.data()
        return records[0].get("deleted", 0) if records else 0

    async def get_stats(self, tenant_id: str | None = None) -> dict:
        """统计；传入 tenant_id 则仅统计该租户，否则全局（仅 admin stats 用）。"""
        if not self._driver_for(write=False):
            return {"total_entities": 0, "total_relations": 0}
        if tenant_id:
            tid = resolve_tenant_id(tenant_id)
            entity_count = await self.execute_cypher(
                "MATCH (e:Entity {tenant_id: $tenant_id}) RETURN count(e) AS cnt",
                {"tenant_id": tid},
                tenant_id=tid,
            )
            rel_count = await self.execute_cypher(
                "MATCH (:Entity {tenant_id: $tenant_id})-[r]->(:Entity {tenant_id: $tenant_id}) "
                "RETURN count(r) AS cnt",
                {"tenant_id": tid},
                tenant_id=tid,
            )
            return {
                "total_entities": entity_count[0]["cnt"] if entity_count else 0,
                "total_relations": rel_count[0]["cnt"] if rel_count else 0,
                "tenant_id": tid,
            }
        # 全局：内部会话直接跑，不走 require_tenant 门禁
        async with self._driver_for(write=False).session() as session:
            er = await (await session.run("MATCH (e:Entity) RETURN count(e) AS cnt")).data()
            rr = await (await session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")).data()
        return {
            "total_entities": er[0]["cnt"] if er else 0,
            "total_relations": rr[0]["cnt"] if rr else 0,
        }
