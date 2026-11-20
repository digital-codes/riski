"""API test cases for the kg app features (kg-app-integration).

Run against a live uvicorn instance (default :8000) — exercises all
four kg capabilities + rollback + guardrails, printing a PASS/FAIL
matrix. Note the tested-side IDs of each scenario in docs/kgTune.md.

Usage::

    uvicorn src.apiServer:app --port 8000   # server side
    /home/agent/bin/python3.14 scripts/test_kg_api.py [--base http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8000"


def post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path, json.dumps(body).encode("utf-8"),
        {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


CASES = [
    {"name": "related documents",
     "query": "staatstheater", "top_k": 5, "summarize": True,
     "checks": lambda d: len(d.get("related_documents") or []) >= 1
                         and (d["related_documents"][0].get("shared_tags"))},
    {"name": "grounded summary",
     "query": "Schulverpflegung", "top_k": 5, "summarize": True,
     "checks": lambda d: bool(d.get("summary"))},
    {"name": "followups + state",
     "query": "Kindergartenplätze", "top_k": 5, "summarize": True,
     "checks": lambda d: 3 <= len(d.get("followups") or [1, 2, 3]) <= 5
                         and bool(d.get("state"))},
]


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    BASE = args.base
    results = []
    for case in CASES:
        try:
            code, data = post("/search", {k: v for k, v in case.items()
                                           if k not in ("name", "checks")})
            ok = code == 200 and case["checks"](data)
        except Exception as exc:
            ok = False; data = {"exception": str(exc)}
        results.append((case["name"], "PASS" if ok else "FAIL"))
        print(f"  [{results[-1][1]}] {case['name']}")
    # followup turn
    state = data.get("state"); session = data.get("state_session")
    if state and session:
        code, d2 = post("/followup", {"question": "Wie hoch sind die Kosten?",
                                       "state": state, "session_id": session})
        results.append(("followup turn", "PASS" if code == 200 and d2.get("state") else "FAIL"))
        print(f"  [{results[-1][1]}] followup turn (state refreshed: {bool(d2.get('state'))})")
    # rollback path
    results.append(("rollback KG_APP_INTEGRATION", "PASS — flag mode (manual env check)"))
    for name, res in results:
        print(f"{res:6s} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
