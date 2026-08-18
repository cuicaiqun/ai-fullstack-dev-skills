"""入库异步任务持久化（Postgres / 内存）。"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
TERMINAL = {STATUS_SUCCEEDED, STATUS_FAILED}


@dataclass
class IngestJob:
    job_id: str
    status: str
    file_name: str
    file_path: str
    doc_id: str
    visibility: str
    user_id: str
    tenant_id: str
    idempotency_key: str = ""
    content_hash: str = ""
    error: str = ""
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IngestJobStore:
    backend: str = "memory"

    def init(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def create(self, job: IngestJob) -> IngestJob:
        raise NotImplementedError

    def get(self, job_id: str) -> IngestJob | None:
        raise NotImplementedError

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[IngestJob]:
        raise NotImplementedError

    def mark_running(self, job_id: str) -> IngestJob | None:
        raise NotImplementedError

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> IngestJob | None:
        raise NotImplementedError

    def mark_failed(self, job_id: str, error: str) -> IngestJob | None:
        raise NotImplementedError


class MemoryIngestJobStore(IngestJobStore):
    backend = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, IngestJob] = {}

    def init(self) -> None:
        logger.warning("Ingest job store using in-memory backend")

    def create(self, job: IngestJob) -> IngestJob:
        with self._lock:
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return IngestJob(**asdict(job)) if job else None

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[IngestJob]:
        with self._lock:
            rows = list(self._jobs.values())
        if user_id:
            rows = [j for j in rows if j.user_id == user_id]
        if tenant_id:
            rows = [j for j in rows if j.tenant_id == tenant_id]
        rows.sort(key=lambda j: j.created_at, reverse=True)
        return [IngestJob(**asdict(j)) for j in rows[:limit]]

    def mark_running(self, job_id: str) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.status = STATUS_RUNNING
            job.started_at = time.time()
            job.updated_at = job.started_at
            return IngestJob(**asdict(job))

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            now = time.time()
            job.status = STATUS_SUCCEEDED
            job.result = result
            job.error = ""
            job.finished_at = now
            job.updated_at = now
            return IngestJob(**asdict(job))

    def mark_failed(self, job_id: str, error: str) -> IngestJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            now = time.time()
            job.status = STATUS_FAILED
            job.error = error[:4000]
            job.finished_at = now
            job.updated_at = now
            return IngestJob(**asdict(job))


class PostgresIngestJobStore(IngestJobStore):
    backend = "postgres"

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._engine: Any = None

    def init(self) -> None:
        from sqlalchemy import create_engine, text

        self._engine = create_engine(self._dsn, pool_pre_ping=True, pool_size=5, max_overflow=10)
        ddl = """
        CREATE TABLE IF NOT EXISTS ingest_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            file_name TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL DEFAULT '',
            doc_id TEXT NOT NULL DEFAULT '',
            visibility TEXT NOT NULL DEFAULT 'tenant',
            user_id TEXT NOT NULL DEFAULT '',
            tenant_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            result_json JSONB,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL,
            started_at DOUBLE PRECISION,
            finished_at DOUBLE PRECISION
        );
        CREATE INDEX IF NOT EXISTS idx_ingest_jobs_user_created
            ON ingest_jobs (user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status
            ON ingest_jobs (status, created_at DESC);
        """
        with self._engine.begin() as conn:
            for stmt in ddl.split(";"):
                s = stmt.strip()
                if s:
                    conn.execute(text(s))
        logger.info("Postgres ingest job store initialized")

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def _row_to_job(self, row: Any) -> IngestJob:
        mapping = row._mapping if hasattr(row, "_mapping") else dict(row)
        result = mapping.get("result_json")
        if isinstance(result, str):
            result = json.loads(result)
        return IngestJob(
            job_id=mapping["job_id"],
            status=mapping["status"],
            file_name=mapping["file_name"],
            file_path=mapping["file_path"],
            doc_id=mapping["doc_id"],
            visibility=mapping["visibility"],
            user_id=mapping["user_id"],
            tenant_id=mapping["tenant_id"],
            idempotency_key=mapping.get("idempotency_key") or "",
            content_hash=mapping.get("content_hash") or "",
            error=mapping.get("error") or "",
            result=result,
            created_at=float(mapping["created_at"]),
            updated_at=float(mapping["updated_at"]),
            started_at=float(mapping["started_at"]) if mapping.get("started_at") is not None else None,
            finished_at=float(mapping["finished_at"]) if mapping.get("finished_at") is not None else None,
        )

    def create(self, job: IngestJob) -> IngestJob:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ingest_jobs (
                        job_id, status, file_name, file_path, doc_id, visibility,
                        user_id, tenant_id, idempotency_key, content_hash, error,
                        result_json, created_at, updated_at, started_at, finished_at
                    ) VALUES (
                        :job_id, :status, :file_name, :file_path, :doc_id, :visibility,
                        :user_id, :tenant_id, :idempotency_key, :content_hash, :error,
                        CAST(:result_json AS jsonb), :created_at, :updated_at, :started_at, :finished_at
                    )
                    """
                ),
                {
                    **asdict(job),
                    "result_json": json.dumps(job.result, ensure_ascii=False) if job.result else None,
                },
            )
        return job

    def get(self, job_id: str) -> IngestJob | None:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ingest_jobs WHERE job_id = :id"),
                {"id": job_id},
            ).fetchone()
            return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[IngestJob]:
        from sqlalchemy import text

        clauses = []
        params: dict[str, Any] = {"lim": limit}
        if user_id:
            clauses.append("user_id = :uid")
            params["uid"] = user_id
        if tenant_id:
            clauses.append("tenant_id = :tid")
            params["tid"] = tenant_id
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM ingest_jobs {where} ORDER BY created_at DESC LIMIT :lim"),
                params,
            ).fetchall()
            return [self._row_to_job(r) for r in rows]

    def mark_running(self, job_id: str) -> IngestJob | None:
        from sqlalchemy import text

        now = time.time()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ingest_jobs
                    SET status = :st, started_at = :now, updated_at = :now
                    WHERE job_id = :id
                    """
                ),
                {"st": STATUS_RUNNING, "now": now, "id": job_id},
            )
        return self.get(job_id)

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> IngestJob | None:
        from sqlalchemy import text

        now = time.time()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ingest_jobs
                    SET status = :st, result_json = CAST(:res AS jsonb), error = '',
                        finished_at = :now, updated_at = :now
                    WHERE job_id = :id
                    """
                ),
                {
                    "st": STATUS_SUCCEEDED,
                    "res": json.dumps(result, ensure_ascii=False),
                    "now": now,
                    "id": job_id,
                },
            )
        return self.get(job_id)

    def mark_failed(self, job_id: str, error: str) -> IngestJob | None:
        from sqlalchemy import text

        now = time.time()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ingest_jobs
                    SET status = :st, error = :err, finished_at = :now, updated_at = :now
                    WHERE job_id = :id
                    """
                ),
                {"st": STATUS_FAILED, "err": error[:4000], "now": now, "id": job_id},
            )
        return self.get(job_id)


def new_job_id() -> str:
    return uuid.uuid4().hex


def create_ingest_job_store(dsn: str | None = None) -> IngestJobStore:
    from config import settings

    resolved = (dsn if dsn is not None else settings.state_store_dsn or "").strip()
    if not resolved:
        store: IngestJobStore = MemoryIngestJobStore()
        store.init()
        return store
    try:
        store = PostgresIngestJobStore(resolved)
        store.init()
        return store
    except Exception:
        logger.exception("Failed to init Postgres ingest job store; falling back to memory")
        store = MemoryIngestJobStore()
        store.init()
        return store
