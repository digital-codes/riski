#!/usr/bin/env python3
"""Capture the canned initial response for the frontend's default query
(change: sanitize-queries-and-initial-response).

Runs the real staged pipeline for `frontend.default_query`
(config/instance.yaml) once and writes every payload the work page's
initial render consumes to app/src/assets/sampleData.json:

- stage-1 fields (query, top_files, matched_entities, facets,
  applied_filters)
    - timeline (full scope — the timeline pane is scope-independent)
- graph: the `documents` scope with `expandable_types` (the default view)
- summary + summary_refused
- geo_available + the geo FeatureCollection

The frontend serves this file directly for the default query (no backend
retrieval cycle) and as the offline fallback. `sessionId` is null and
`snapshot: true` marks the snapshot mode.

Usage: python3 scripts/capture_initial_response.py [--output PATH]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", default=str(REPO / "app" / "src" / "assets" / "sampleData.json"))
    args = ap.parse_args()

    from src.instanceConfig import get_instance_config

    cfg = get_instance_config()
    query = ((cfg.get("frontend") or {}).get("default_query")
             or "wo liegt die Governance für Digitalisierung bei der Stadt Karlsruhe")
    print(f"capturing snapshot for default query: {query!r}")

    from src.pgResultSummarizer import ResultSummarizer
    from src.pgTimeline import get_db_session, timeline_stage, graph_stage
    from src.apiServer import _stage1_search_fn

    session = get_db_session()
    try:
        stage1 = _stage1_search_fn(session, query, top_k=10)
        stage1.pop("sessionId", None)
        stage2 = timeline_stage(session, stage1)
        stage3 = graph_stage(session, stage1, stage2)
        ResultSummarizer(session).summarize(stage1)

        from src.pgGeo import collect_geo
        from src.db import get_engine

        # the snapshot carries the DOCUMENTS scope (the default view) and
        # its geo references — matching what the live default view shows
        graph = stage3.get("graph_documents") or stage3["graph"]
        engine = get_engine(readonly=True)
        file_keys = [n["oparlKey"] for n in graph.get("nodes", [])
                     if n.get("type") in ("File", "AuxFile") and n.get("oparlKey")]
        agenda_keys = [n["oparlKey"] for n in graph.get("nodes", [])
                       if n.get("type") == "AgendaItem" and n.get("oparlKey")]
        fc = collect_geo(engine, agenda_keys, file_keys)
        # the documents scope's own availability — the stage3 flag describes
        # the FULL scope and would show a map the snapshot cannot fill
        geo_available = bool((fc or {}).get("features"))
    finally:
        session.close()

    from src.graphModel import expandable_types

    snapshot = {
        "query": query,
        "top_files": stage1.get("top_files") or [],
        "matched_entities": stage1.get("matched_entities") or [],
        "facets": stage1.get("facets") or {},
        "applied_filters": stage1.get("applied_filters") or [],
        "timeline": stage2.get("timeline") or [],
        "graph": graph,
        "geo_available": geo_available,
        "geo": fc,
        "summary": stage1.get("summary"),
        "summary_refused": stage1.get("summary_refused") or [],
        "sessionId": None,
        "snapshot": True,
        "expandable_types": expandable_types(),
        "captured_at": dt.datetime.now().isoformat(timespec="seconds"),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KiB): "
          f"{len(snapshot['top_files'])} top_files, "
          f"{len(snapshot['graph'].get('nodes', []))} graph nodes, "
          f"summary={'yes' if snapshot['summary'] else 'no'}, "
          f"geo features={len((snapshot['geo'] or {}).get('features', []))}")


if __name__ == "__main__":
    main()
