"""P0-2：入库存储结果判定（向量 + 图谱任一步失败则不得 ready）。"""

from __future__ import annotations

from typing import Any


def assess_ingest_storage(state: dict[str, Any]) -> tuple[bool, str]:
    """
    返回 (ok, error_detail)。
    - 有 chunk 且 embeddings 可用时，向量写入必须成功
    - 有抽取结果且图谱服务已连接时，图谱写入必须成功
    """
    if state.get("store_ok") is False:
        return False, str(state.get("store_error") or "storage failed")

    chunks = state.get("chunks") or []
    if not chunks:
        return False, "no chunks to store"

    vectors_ok = state.get("vectors_ok")
    if vectors_ok is False:
        return False, str(state.get("vectors_error") or "vector store failed")

    # embeddings 不可用时显式 skipped → 不得 ready
    if state.get("vectors_skipped"):
        return False, str(state.get("vectors_error") or "embeddings unavailable")

    if vectors_ok is not True and int(state.get("vectors_stored") or 0) <= 0:
        return False, "vectors not stored"

    graph_required = bool(state.get("graph_required"))
    if graph_required and state.get("graph_ok") is not True:
        return False, str(state.get("graph_error") or "knowledge graph store failed")

    return True, ""
