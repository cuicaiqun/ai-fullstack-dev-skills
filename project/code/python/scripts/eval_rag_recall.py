#!/usr/bin/env python3
"""RAG 召回/答案评测：对已入库手册跑固定问句，统计命中率。

用法（API 已启动）:
  cd code/python
  python scripts/eval_rag_recall.py --base-url http://127.0.0.1:8080 \\
    --user admin --password admin123

可选先上传评测文档:
  python scripts/eval_rag_recall.py --ingest-first
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SET = ROOT / "evals" / "qa_set.json"
DEFAULT_DOC = ROOT / "evals" / "handbook.md"


def login(client: httpx.Client, user: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": user, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def wait_task(client: httpx.Client, headers: dict, task_id: str, timeout: float = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/ingest/tasks/{task_id}", headers=headers)
        r.raise_for_status()
        body = r.json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(2)
    raise TimeoutError(f"ingest task timeout: {task_id}")


def ingest(client: httpx.Client, headers: dict, path: Path) -> None:
    with path.open("rb") as f:
        r = client.post(
            "/api/ingest/upload",
            headers=headers,
            files={"file": (path.name, f, "text/markdown")},
            data={"visibility": "tenant"},
        )
    if r.status_code == 202:
        task_id = r.json()["task_id"]
        print(f"ingest queued task_id={task_id}")
        done = wait_task(client, headers, task_id)
        if done["status"] != "succeeded":
            raise RuntimeError(f"ingest failed: {done}")
        print("ingest succeeded", done.get("result"))
    else:
        r.raise_for_status()
        print("ingest sync", r.json())


def score_case(answer: str, sources: list, case: dict) -> dict:
    ans_ok = any(tok in (answer or "") for tok in case.get("must_contain_any") or [])
    blob = " ".join(
        f"{s.get('content','')} {s.get('source','')}" for s in (sources or [])
    )
    expect = case.get("expect_source_substr") or []
    recall_hits = sum(1 for tok in expect if tok in blob)
    recall_ok = recall_hits >= max(1, len(expect) // 2) if expect else bool(sources)
    return {
        "id": case["id"],
        "answer_ok": ans_ok,
        "recall_ok": recall_ok,
        "recall_hits": recall_hits,
        "answer_preview": (answer or "")[:160],
        "n_sources": len(sources or []),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--qa-set", type=Path, default=DEFAULT_SET)
    ap.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    ap.add_argument("--ingest-first", action="store_true")
    args = ap.parse_args()

    qa_set = json.loads(args.qa_set.read_text(encoding="utf-8"))
    cases = qa_set["cases"]

    with httpx.Client(base_url=args.base_url, timeout=300.0) as client:
        token = login(client, args.user, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        if args.ingest_first:
            ingest(client, headers, args.doc)

        rows = []
        for case in cases:
            r = client.post(
                "/api/qa/ask",
                headers=headers,
                json={"question": case["question"]},
            )
            r.raise_for_status()
            body = r.json()
            row = score_case(body.get("answer", ""), body.get("sources", []), case)
            row["grounded"] = body.get("grounded")
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

    answer_rate = sum(1 for r in rows if r["answer_ok"]) / max(1, len(rows))
    recall_rate = sum(1 for r in rows if r["recall_ok"]) / max(1, len(rows))
    summary = {
        "n": len(rows),
        "answer_hit_rate": round(answer_rate, 3),
        "recall_hit_rate": round(recall_rate, 3),
    }
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    # 真实验收门槛：至少一半问句答案命中 + 召回命中
    return 0 if answer_rate >= 0.5 and recall_rate >= 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
