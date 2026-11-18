"""Compare language models for the kg statement extraction (task 7.1).

Runs the SAME fixed sample pairs through the candidate models and
scores the extracted statements against their cross-check verdicts
(d3:2b SystemOne noul) plus a field-fill rate. The result report lands
in ``results/kg_model_selection.md``.

Candidates (docs/kg_building.md): granite4.2:8b, qwen3.5:4b,
mistral:latest (local ollama) plus the cloud ``olc`` default
(gpt-oss:20b-cloud) when it proves fastest (bench 2026-11-17).

IMPORTANT (verified on this box): clean off the previous runner before
each model switch — ``curl localhost:11434/api/generate -d
'{"model":"<m>","keep_alive":0}'`` — concurrent hot models share
GPU/CPU and stall everything.

Usage::

    python -m src.kg.kgModelSelect --limit 8
    python -m src.kg.kgModelSelect --limit 8 --models granite4.2:8b,mistral:latest
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import json
import subprocess
import time
from datetime import date

from src.db import get_engine
from src.kg.kgRemote import LANGUAGE_MODELS, KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatements import StatementExtractor
from src.kg.kgStatus import StatusTicker

DEFAULT_STORE = "results/kg_statements.sqlite"
DEFAULT_REPORT = "results/kg_model_selection.md"


def stop_local_model(model: str) -> None:
    try:
        subprocess.run(
            [
                "curl", "-s", "http://localhost:11434/api/generate",
                "-d", json.dumps({"model": model, "keep_alive": 0}), "-X", "POST",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except Exception:
        pass


def sample_pairs(store: KgStore, limit: int) -> list[dict]:
    """Fixed sample: pairs WITH response docs first (both stages tested)."""
    rows = store.conn.execute(
        """
        SELECT p.pair_key, p.paper_key, p.meeting_key, p.meeting_date,
               p.outcome
        FROM pairs p
        WHERE p.status = 'identified'
        ORDER BY CASE WHEN EXISTS (
            SELECT 1 FROM pair_documents d
             WHERE d.pair_key = p.pair_key AND d.role = 'response'
        ) THEN 0 ELSE 1 END, p.pair_key
        LIMIT :n
        """,
        {"n": limit},
    ).fetchall()
    return [dict(r) for r in rows]


def run_model(
    model: str | None,
    endpoint: str,
    pairs: list[dict],
    store: KgStore,
    conn,
) -> dict:
    """Extract + cross-check each sample pair; return metrics."""
    remote = KgRemote(endpoint, chat_model=model)
    extractor = StatementExtractor(remote, model) if endpoint == "ollama" else remote
    from src.kg.kgCrossCheck import check_pair
    from src.kg.kgStatements import texts_for_role

    stats = {
        "model": model or f"{endpoint}:default",
        "endpoint": endpoint,
        "pairs": 0, "request_ok": 0, "response_ok": 0,
        "field_fill": [], "noul": [], "failed": 0, "wall": 0.0,
    }
    for pair in pairs:
        t0 = time.time()
        docs = store.documents_for_pair(pair["pair_key"])
        req_keys = [d["doc_key"] for d in docs if d["role"] in ("request", "modification")]
        resp_keys = [d["doc_key"] for d in docs if d["role"] == "response"]
        src_model = model  # per-call model on ollama; None = endpoint default on cloud
        try:
            body, _ = texts_for_role(conn, req_keys)
            if endpoint == "ollama":
                req = extractor.extract("request", body)
            else:
                req = remote.chat_json(extractor_messages("request", body))
            stats["request_ok"] += 1
            stats["field_fill"].append(
                sum(1 for v in req.values() if str(v or "").strip())
                / max(len(req), 1)
            )
        except Exception:
            stats["failed"] += 1
            continue
        if resp_keys:
            body, _ = texts_for_role(conn, resp_keys)
            try:
                if endpoint == "ollama":
                    resp = extractor.extract("response", body)
                else:
                    resp = remote.chat_json(extractor_messages("response", body))
                stats["response_ok"] += 1
            except Exception:
                stats["failed"] += 1
        # cross-check the response/body verdict with SystemOne
        try:
            from src.kg.kgCrossCheck import VERDICT_SRC_AND_SUMMARY  # noqa: F401
            record = check_pair(remote, conn, store, pair["pair_key"])
            if record.get("reason", "").startswith("systemone noul="):
                stats["noul"].append(
                    float(record["reason"].split("=")[1])
                )
            if record.get("verdict") == "failed":
                stats["failed"] += 1
        except Exception:
            pass
        stats["wall"] += time.time() - t0
    stats["field_fill_avg"] = (
        round(sum(stats["field_fill"]) / len(stats["field_fill"]), 3)
        if stats["field_fill"] else 0.0
    )
    stats["noul_max"] = round(max(stats["noul"]), 3) if stats["noul"] else None
    stats["noul_avg"] = (
        round(sum(stats["noul"]) / len(stats["noul"]), 3) if stats["noul"] else None
    )
    return stats


def extractor_messages(stage: str, body: str) -> list[dict]:
    """Minimal JSON extraction messages for the cloud path."""
    return [
        {"role": "system", "content": (
            "Extrahiere die Kernfakten aus dem deutschen Kommunal-Dokument. "
            "Antworte NUR mit einem JSON-Objekt (Felder: topic, requested_action, "
            "involved_cost, start_date). Fehlende Werte als \"\"."
        )},
        {"role": "user", "content": body[:12000]},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--limit", type=int, default=8, help="sample pairs per model")
    parser.add_argument(
        "--models",
        default=None,
        help="comma-separated model overrides (local ollama names only)",
    )
    parser.add_argument("--skip-olc", action="store_true")
    parser.add_argument(
        "--include-local",
        action="store_true",
        help="also benchmark local ollama candidates (NOT default: the "
        "local ollama runner is retired for kg per user decision "
        "2026-11-18 — cloud OLC only)")
    parser.add_argument("--report", default=DEFAULT_REPORT)
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    pairs = sample_pairs(store, args.limit)
    ticker = StatusTicker()
    ticker.section("modelselect")
    ticker.tick(f"sample pairs: {len(pairs)}", force=True)

    results = []
    # default: OLC cloud only (user decision 2026-11-18). Local ollama
    # candidates require --include-local (runner retired otherwise)
    if not args.skip_olc:
        results.append(run_model(None, "olc", pairs, store, conn))
    if args.include_local:
        for model in (args.models.split(",") if args.models else LANGUAGE_MODELS):
            stop_local_model(model)
            time.sleep(2)
            results.append(run_model(model, "ollama", pairs, store, conn))
            stop_local_model(model)

    lines = [
        f"# kg model selection ({date.today().isoformat()})\n",
        f"sample: {len(pairs)} pairs (response-bearing first)\n",
        "| model | endpoint | wall/pair | request ok | response ok | field fill | noul avg/max | failed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        per_pair = round(r["wall"] / max(r["pairs"], 1), 1)
        lines.append(
            f"| {r['model']} | {r['endpoint']} | {per_pair}s | {r['request_ok']} | "
            f"{r['response_ok']} | {r['field_fill_avg']} | {r['noul_avg']}/{r['noul_max']} | {r['failed']} |"
        )
    # recommendation: best = highest pass/field fill at lowest wall
    scored = sorted(
        results,
        key=lambda r: (-(r["field_fill_avg"]), r["noul_avg"] or 0, r["wall"]),
    )
    lines += [
        "",
        f"**Recommendation:** `{scored[0]['model']}` (best field fill "
        f"{scored[0]['field_fill_avg']} at {round(scored[0]['wall']/max(scored[0]['pairs'],1),1)}s/pair)",
    ]
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    ticker.tick("\n".join(lines[-2:]), force=True)
    print(f"report: {args.report}")
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
