#!/usr/bin/env python3
"""Summary-model performance benchmark: configured chat endpoints vs each other.

Runs the production search (``src.pgTimeline.search_and_build_timeline``),
builds the exact summary prompt via ``src.pgResultSummarizer`` (a spy on
``remote.chat`` captures the messages without spending tokens), then times
RUNS chat calls per (query, model) and averages.

All credentials and endpoints come from ``src/private.py`` (gitignored) —
nothing is hardcoded here.

Usage:
    python3 utils/bench_summary_models.py [-o results.json]

Output: JSON with per-run latencies/tokens and per-model averages, plus a
readable table on stdout.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.pgTimeline import get_db_session, search_and_build_timeline
from src.pgResultSummarizer import ResultSummarizer
from src import remote
import src.private as pr

QUERIES = [
    # frontend default query (config/instance.yaml → frontend.default_query)
    "wo liegt die Governance für Digitalisierung bei der Stadt Karlsruhe",
    # recent example queries (config/intents.yaml choices)
    "was wurde im letzten gemeinderat besprochen",
    "was gibt es neues zum radweg am terrainkurweg",
    "themen rund um die 2. rheinbrücke",
]

MODELS = [
    ("mistral-small-2603 (mistral.ai)", pr.SUMMARY_URL, pr.SUMMARY_MDL, pr.SUMMARY_KEY,
     131_072),
    ("Mistral Small 24B (IONOS)", pr.IO_SUMMARY_URL, pr.IO_SUMMARY_MDL, pr.IO_SUMMARY_KEY,
     32_768),
    ("gpt-oss-120b (IONOS)", pr.IO_SUMMARY_URL, pr.IO_SUMMARY_MDL_ALT, pr.IO_SUMMARY_KEY,
     131_072),
    # local ollama summary model (private.py LOC_SUMMARY_*) — not always
    # available, skipped when unreachable; context limit as configured on
    # the ollama side (num_ctx / OLLAMA_CONTEXT_LENGTH)
    ("ministral-3:8b (local ollama)", getattr(pr, "LOC_SUMMARY_URL", None),
     getattr(pr, "LOC_SUMMARY_MDL", None), getattr(pr, "LOC_SUMMARY_KEY", ""),
     30_000),
]

RUNS = 5
TOP_K = 10  # API default


def build_prompt(session, query):
    """Production search once + capture the exact summary prompt."""
    result = search_and_build_timeline(session, query, top_k=TOP_K)
    captured = {}
    orig_chat = remote.chat

    def spy(messages, **kw):
        captured["messages"] = messages
        return {"content": "[dummy response]"}

    remote.chat = spy
    try:
        ResultSummarizer(session).summarize(result)
    finally:
        remote.chat = orig_chat
    return captured["messages"], len(result.get("top_files") or [])


def build_refine_prompt(session, query):
    """Capture the refinement prompt (matched-chunk context, change:
    fix-result-summarizer) for the same query — the token-heavier pass."""
    result = search_and_build_timeline(session, query, top_k=TOP_K)
    captured = {}
    orig_chat = remote.chat

    def spy(messages, **kw):
        captured["messages"] = messages
        return {"content": "[dummy response]"}

    remote.chat = spy
    try:
        ResultSummarizer(session).summarize(result, force=True, use_full_content=True)
    finally:
        remote.chat = orig_chat
    return captured["messages"], len(result.get("top_files") or [])


def call(messages, url, model, key):
    payload = {"model": model, "temperature": 0.1, "messages": messages}
    t0 = time.perf_counter()
    data = remote._post("chat/completions", payload, timeout=240,
                        base_url=url, api_key=key)
    dt = time.perf_counter() - t0
    usage = data.get("usage") or {}
    return dt, usage.get("prompt_tokens"), usage.get("completion_tokens")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=str(REPO / "results" / "summary_model_bench.json"))
    ap.add_argument("--only", default=None,
                    help="substring filter on the model label (e.g. 'ollama') — "
                         "skips the other endpoints (no re-billing)")
    ap.add_argument("--skip-refine", action="store_true",
                    help="skip the refinement-pass token check")
    args = ap.parse_args()

    session = get_db_session()
    out = {"queries": QUERIES, "runs": RUNS, "top_k": TOP_K, "models": {}}

    for label, url, model, key, ctx in MODELS:
        if args.only and args.only.lower() not in label.lower():
            continue
        print(f"\n=== {label} ===", flush=True)
        if url is None or model is None:
            print("  skipped: not configured", flush=True)
            continue
        per_query = {}
        # availability guard: local endpoints may be down — skip silently
        try:
            msgs, _ = build_prompt(session, QUERIES[0])
            call(msgs, url, model, key)  # warmup (not counted)
        except Exception as exc:  # noqa: BLE001
            print(f"  skipped: endpoint unavailable ({str(exc)[:120]})", flush=True)
            continue
        for q in QUERIES:
            msgs, n_files = build_prompt(session, q)
            runs = []
            for i in range(RUNS):
                dt, pt, ct = call(msgs, url, model, key)
                tps = (ct / dt) if (ct and dt) else None
                runs.append({"s": round(dt, 2), "ptok": pt, "ctok": ct,
                             "tok_s": round(tps, 1) if tps else None})
                print(f"  [{q[:40]}...] run{i + 1}: {dt:.2f}s  {ct} ctok  "
                      f"{tps and round(tps, 1)} tok/s", flush=True)
            entry = {"n_files": n_files, "runs": runs}
            # token-limit check on the token-heavier pass: one refinement
            # call per query — ollama truncates over-long prompts to the
            # context window silently, so a prompt_tokens value at/above
            # ~95% of the limit means content was cut off
            if not args.skip_refine:
                rmsgs, _ = build_refine_prompt(session, q)
                try:
                    _, rpt, rct = call(rmsgs, url, model, key)
                except Exception as exc:  # noqa: BLE001
                    print(f"  refine check failed: {str(exc)[:120]}", flush=True)
                    rpt = None
                entry["refine_ptok"] = rpt
                entry["refine_exceeds_ctx"] = bool(
                    ctx and rpt and rpt >= 0.95 * ctx)
                flag = " ⚠ EXCEEDS CONTEXT" if entry["refine_exceeds_ctx"] else ""
                print(f"  [{q[:40]}...] refine: {rpt} ptok / ctx {ctx}{flag}",
                      flush=True)
            per_query[q] = entry
        lat = [r["s"] for q in per_query for r in per_query[q]["runs"]]
        cts = [r["ctok"] for q in per_query for r in per_query[q]["runs"]]
        tpss = [r["tok_s"] for q in per_query for r in per_query[q]["runs"] if r["tok_s"]]
        out["models"][label] = {
            "ctx_tokens": ctx,
            "per_query": per_query,
            "avg_latency_s": round(statistics.mean(lat), 2),
            "avg_completion_tokens": round(statistics.mean(cts), 1),
            "avg_tok_s": round(statistics.mean(tpss), 1) if tpss else None,
        }
        print(f"  AVG: {out['models'][label]['avg_latency_s']}s, "
              f"{out['models'][label]['avg_completion_tokens']} ctok, "
              f"{out['models'][label]['avg_tok_s']} tok/s", flush=True)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\nDONE — results written to {args.output}", flush=True)


if __name__ == "__main__":
    main()
