"""
P0-4：持久化 QA checkpointer（跨进程重启保留多轮 thread）。

默认 AsyncSqliteSaver（配合 ainvoke）；QA_CHECKPOINT_BACKEND=memory 时回退 MemorySaver。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from config import settings

logger = logging.getLogger(__name__)

_checkpointer: Any = None
_aiosqlite_conn: Any = None


async def init_qa_checkpointer() -> Any:
    """在 FastAPI lifespan / 异步测试中调用。"""
    global _checkpointer, _aiosqlite_conn
    await close_qa_checkpointer()

    backend = (settings.qa_checkpoint_backend or "sqlite").strip().lower()
    if backend == "memory":
        _checkpointer = MemorySaver()
        logger.info("QA checkpointer backend=memory")
        return _checkpointer

    path = Path(settings.qa_checkpoint_path or "./data/qa_checkpoints.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    _aiosqlite_conn = await aiosqlite.connect(str(path))
    saver = AsyncSqliteSaver(_aiosqlite_conn)
    await saver.setup()
    _checkpointer = saver
    logger.info("QA checkpointer backend=sqlite path=%s", path)
    return _checkpointer


def get_qa_checkpointer() -> Any:
    if _checkpointer is None:
        raise RuntimeError("QA checkpointer not initialized; call await init_qa_checkpointer()")
    return _checkpointer


async def close_qa_checkpointer() -> None:
    global _checkpointer, _aiosqlite_conn
    _checkpointer = None
    if _aiosqlite_conn is not None:
        try:
            await _aiosqlite_conn.close()
        except Exception:
            logger.exception("close qa checkpoint sqlite failed")
        _aiosqlite_conn = None
