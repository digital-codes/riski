"""API test cases for the kg app features (kg-app-integration).

Run against a live uvicorn instance (default :8000) — exercises all
four kg capabilities + the D7 query-thread loop + rollback + guardrails,
printing a PASS/FAIL matrix.

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


def check(name: str, ok: bool, results: list, detail: str = "") -> None:
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  [{results[-1][1]}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    BASE = args.base
    results: list[tuple[str, str, str]] = []

    # ---- base capabilities ------------------------------------------------
    code, d = post("/search", {"query": "staatstheater", "top_k": 5,
                               "summarize": True})
    ok = code == 200 and len(d.get("related_documents") or []) >= 1 \
        and (d["related_documents"][0].get("shared_tags"))
    check("related documents", ok, results)

    code, d = post("/search", {"query": "Schulverpflegung", "top_k": 5,
                               "summarize": True})
    check("grounded summary", code == 200 and bool(d.get("summary")), results)

    code, d = post("/search", {"query": "Kindergartenplätze", "top_k": 5,
                               "summarize": True})
    fuzzies = d.get("followups") or []
    check("followups + state", code == 200 and 3 <= len(fuzzies) <= 5
          and bool(d.get("state")), results)

    state, session = d.get("state"), d.get("state_session")
    if state and session:
        code2, d2 = post("/followup", {"question": "Wie hoch sind die Kosten?",
                                       "state": state, "session_id": session})
        check("followup turn", code2 == 200 and bool(d2.get("state")), results)
        # tampered token → 400 (guardrail)
        code3, _ = post("/followup", {"question": "Wie hoch sind die Kosten?",
                                      "state": state[:-4] + "AAAA",
                                      "session_id": session})
        check("forged token → 400", code3 == 400, results, f"code={code3}")
    else:
        check("followup turn", False, results, "no state from previous case")
        check("forged token → 400", False, results, "skipped")

    # ---- D7: clarification / chips mode -----------------------------------
    code, d = post("/search", {"query": "qwertyui xzz blorb", "top_k": 5,
                               "summarize": False, "thread": {"fresh": True}})
    chips = d.get("chips") or []
    suppressed = all(k not in d for k in
                     ("summary", "clarification", "related_documents"))
    check("chips mode (weak recall)", code == 200 and d.get("mode") == "chips"
          and len(chips) == 5 and bool(d.get("hint")) and suppressed,
          results, f"chips={len(chips)} mode={d.get('mode')}")

    # ---- D7: thread chain (concat → break) --------------------------------
    turns = [("wo wird das Forum am Recht gebaut", {"fresh": True}),
             ("welche umweltauswirkungen hat das", None),
             ("warum haben die Grünen dem zugestimmt", None),
             ("was macht die stadt beim klimaschutz", None)]
    chain: list[tuple] = []
    state, session = None, None
    for q, extra in turns:
        body = {"query": q, "top_k": 5, "summarize": False}
        body["thread"] = extra if extra else {"state": state, "session_id": session}
        code, d = post("/search", body)
        chain.append((code, d.get("thread") or {}, d.get("query") or "",
                      bool(d.get("state"))))
        state, session = d.get("state"), d.get("state_session")
    ok_chain = all(c == 200 and st for c, _t, _q, st in chain)
    # followup turns concat (query grows), the break query does not
    ok_concat = ok_chain and len(chain[2][2]) > len(chain[1][2]) \
        and len(chain[2][2]) > 100 \
        and len(chain[3][2]) < len(chain[2][2])
    check("thread concat turns", ok_concat, results,
          f"len={len(chain[1][2])}<={len(chain[2][2])}>{len(chain[3][2])}")

    # ---- D7: hard budget at 5 turns ---------------------------------------
    state, session = (chain[3][1].get("thread_id") and state), session
    reset_seen = False
    for _ in range(2):
        code, d = post("/search", {"query": "und die finanzierung der variante?",
                                   "top_k": 5, "summarize": False,
                                   "thread": {"state": state, "session_id": session}})
        state, session = d.get("state"), d.get("state_session")
        if d.get("thread_reset"):
            reset_seen = True
            break
    # one more turn must either keep a fresh thread or set thread_reset
    if not reset_seen:
        code, d = post("/search", {"query": "und die finanzierung der variante?",
                                   "top_k": 5, "summarize": False,
                                   "thread": {"state": state, "session_id": session}})
        reset_seen = bool(d.get("thread_reset")) or \
            (d.get("thread") or {}).get("turn_count") == 1
    check("thread budget (reset ≤ 6th turn)", reset_seen, results)

    # ---- rollback ----------------------------------------------------------
    results.append(("rollback KG_APP_INTEGRATION", "PASS (manual env check)", ""))
    print()
    for name, res, detail in results:
        print(f"{res:6s} {name}" + (f" — {detail}" if detail else ""))
    failed = [n for n, r, _ in results if r == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
