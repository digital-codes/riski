#!/usr/bin/env python3
"""Extended Intent Decoder Tests (choice/noul/score/slot).

Reads endpoint/model from src/private.py (SYSONE_URL / SYSONE_MDL) with
CLI overrides:

    python utils/test_intent_decoder_extended.py
    python utils/test_intent_decoder_extended.py --url http://localhost:11434/v1/systemone --model d3:2b

Modes: choice | noul_multi | score | slot
Negative cases: intents may carry a `negative: [utterances]` list; an
utterance that belongs to no intent is expected to resolve to the fallback
intent (the intent marked `fallback: true`, default `search_topic`).
Slot mode measures slot-criteria extraction accuracy (gremium slot) over
utterances that name a known gremium.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

_REPO_ROOT = Path(__file__).parent.parent
_DEFAULT_SYSTEMONE_URL = "http://localhost:11434/v1/systemone"
_DEFAULT_MODELS = ["tev1:0.8b", "d3:2b"]

SYSTEMONE_URL = _DEFAULT_SYSTEMONE_URL


def _load_private():
    import sys

    sys.path.insert(0, str(_REPO_ROOT))
    try:
        import src.private as pr

        return pr
    except Exception:
        return None


def load_config():
    config_path = _REPO_ROOT / "config" / "intents.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def fallback_intent_name(config: dict) -> str:
    for intent in config["intents"]:
        if intent.get("fallback"):
            return intent["name"]
    return "search_topic"


def generate_test_cases(config: dict):
    cases = []
    fallback = fallback_intent_name(config)
    for intent in config["intents"]:
        for choice in intent.get("choices", []) or []:
            cases.append({"query": choice, "expected": intent["name"]})
        for neg in intent.get("negative", []) or []:
            cases.append({"query": neg, "expected": fallback, "negative": True})
    import random

    random.shuffle(cases)
    return cases


def gremium_criteria(config: dict):
    """Slot-criteria list for the gremium slot: config hard values + DB org
    names (DB is optional — absent/unreachable DB degrades to config only)."""
    names = []
    for intent in config["intents"]:
        for slot_name, slot in (intent.get("slots") or {}).items():
            if slot_name != "gremium":
                continue
            for src in slot.get("sources", []) or []:
                if "hard" in src:
                    names.extend(src["hard"])
    db_names = _db_gremium_names()
    for n in db_names:
        if n not in names:
            names.append(n)
    return [n.lower().strip() for n in names]


def _db_gremium_names():
    try:
        import sys

        sys.path.insert(0, str(_REPO_ROOT))
        from sqlalchemy import text

        from src.db import get_engine

        engine = get_engine(readonly=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    'SELECT coalesce("shortname", "name") FROM "Organization" '
                    "WHERE lower(\"name\") ~ '(ortschaftsrat|gemeinderat|ausschuss|beirat)' "
                    "ORDER BY 1"
                )
            ).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception as exc:  # DB optional for the harness
        console.print(f"[yellow]  (DB vocab unavailable: {exc})[/yellow]")
        return []


async def decode_one(
    client: httpx.AsyncClient,
    model: str,
    intents: list,
    case: dict,
    mode: str = "choice",
    auth_header: dict | None = None,
    gremium_list: list | None = None,
):
    is_slot = mode == "slot"
    build_mode = "score" if is_slot else mode

    if build_mode == "choice":
        criteria = {}
        for intent in intents:
            criteria[intent["name"]] = intent["description"]
        question = {
            "intent": {
                "type": "choice",
                "instructions": "Welcher Intent passt am besten zur Benutzeranfrage? Wähle den passendsten aus.",
                "criteria": criteria,
            }
        }
        num_options = len(criteria)
    elif build_mode == "noul_multi":
        questions = {}
        for intent in intents:
            questions[intent["name"]] = {
                "type": "noul",
                "instructions": f"Ist der Intent '{intent['name']}' gemeint? ({intent['description']})",
                "criteria": {"true": "Ja, passt", "false": "Nein, passt nicht"},
            }
        question = questions
        num_options = len(questions) * 2  # true/false per question
    elif build_mode == "score":
        if is_slot:
            # score questions allow at most 10 criteria (SystemOne protocol);
            # slot vocabularies are larger, so slot mode uses choice
            criteria = {v: f"Gremium {v}" for v in (gremium_list or [])}
            question = {
                "slot_gremium": {
                    "type": "choice",
                    "instructions": "Welches Gremium (Rat, Ortschaftsrat, Ausschuss) ist in der Benutzeranfrage gemeint?",
                    "criteria": criteria,
                }
            }
        else:
            criteria = [intent["name"] + ": " + intent["description"] for intent in intents]
            question = {
                "intent": {
                    "type": "score",
                    "instructions": "Welcher Intent passt am besten zur Benutzeranfrage?",
                    "criteria": criteria,
                }
            }
        num_options = len(criteria)
    else:
        criteria = {}
        for intent in intents:
            criteria[intent["name"]] = intent["description"]
        question = {
            "intent": {
                "type": "choice",
                "instructions": "Welcher Intent passt am besten zur Benutzeranfrage? Wähle den passendsten aus.",
                "criteria": criteria,
            }
        }
        num_options = len(criteria)

    payload = {
        "model": model,
        "state": case["query"].lower(),
        "questions": question,
    }
    payload_size = len(json.dumps(payload).encode("utf-8"))

    start = time.time()
    try:
        resp = await client.post(
            SYSTEMONE_URL, json=payload, timeout=300.0, headers=auth_header or {}
        )
        resp.raise_for_status()
        data = resp.json()
        answers = data.get("answers", {})

        if build_mode == "choice":
            pred = answers.get("intent", {}).get("choice", "unknown")
        elif build_mode == "noul_multi":
            best = None
            best_score = -1
            for intent in intents:
                noul_score = answers.get(intent["name"], {}).get("noul", 0)
                if noul_score > best_score:
                    best_score = noul_score
                    best = intent["name"]
            pred = best or "unknown"
        elif build_mode == "score":
            if is_slot:
                pred = answers.get("slot_gremium", {}).get("choice", "unknown")
            else:
                key = "intent"
                score = answers.get(key, {}).get("score", -1)
                legend = answers.get(key, {}).get("legend", {})
                if legend:
                    idx = round(score)
                    if idx < 0:
                        idx = 0
                    if idx >= num_options:
                        idx = num_options - 1
                    pred = intents[idx]["name"]
                else:
                    pred = "unknown"
        else:
            pred = "unknown"

        # normalize comparison space
        if is_slot:
            correct = str(pred).lower().strip() == str(case["expected_slot"]).lower().strip()
        else:
            correct = pred == case["expected"]

        return {
            "query": case["query"],
            "expected": case.get("expected_slot", case["expected"]),
            "predicted": pred,
            "correct": correct,
            "latency": time.time() - start,
            "mode": mode,
            "payload_size_bytes": payload_size,
            "num_options": num_options,
        }
    except Exception as e:
        return {
            "query": case["query"],
            "expected": case.get("expected_slot", case["expected"]),
            "predicted": "error",
            "correct": False,
            "latency": time.time() - start,
            "error": str(e),
            "mode": mode,
            "payload_size_bytes": payload_size,
            "num_options": num_options,
        }


def slot_cases(config: dict, gremium_list: list):
    """Test cases for slot mode: utterances that explicitly name a known
    gremium; expected = the named gremium (substring match, lowercase)."""
    cases = []
    gl = [g.lower() for g in gremium_list]
    for intent in config["intents"]:
        for choice in intent.get("choices", []) or []:
            q = choice.lower()
            for g in gl:
                if g and g in q:
                    cases.append({"query": choice, "expected_slot": g})
                    break
    return cases


async def test_model(model: str, config: dict, test_cases: list, mode: str, auth_header=None):
    console.print(f"[bold cyan]Testing model: {model} | Mode: {mode}[/bold cyan]")
    model_start = time.time()
    intents = config["intents"]

    gremium_list = gremium_criteria(config) if mode == "slot" else None
    if mode == "slot":
        test_cases = slot_cases(config, gremium_list)
        console.print(f"  slot cases: {len(test_cases)} over {len(gremium_list)} criteria")

    if not test_cases:
        console.print("  [yellow]no test cases, skipping[/yellow]")
        return {
            "results": [], "accuracy": 0.0, "avg_latency": 0.0,
            "avg_payload_bytes": 0, "avg_num_options": 0, "total_time": 0.0,
            "correct": 0, "total": 0, "mode": mode,
        }

    async with httpx.AsyncClient() as client:
        tasks = [
            decode_one(client, model, intents, case, mode, auth_header, gremium_list)
            for case in test_cases
        ]
        results = await asyncio.gather(*tasks)

    model_time = time.time() - model_start
    correct = sum(1 for r in results if r["correct"])
    acc = correct / len(results) * 100
    avg_lat = sum(r["latency"] for r in results) / len(results)
    avg_payload = sum(r["payload_size_bytes"] for r in results) / len(results)
    avg_opts = sum(r["num_options"] for r in results) / len(results)

    for i, r in enumerate(results, 1):
        status = "[green]✓[/green]" if r["correct"] else "[red]✗[/red]"
        console.print(
            f"  {status} [{i}/{len(results)}] '{r['query'][:40]}...' -> {r['predicted']} (exp: {r['expected']}, {r['latency']:.2f}s, {r['payload_size_bytes']}B, opts:{r['num_options']})"
        )

    console.print(
        f"\n  [bold]Accuracy: {acc:.1f}% ({correct}/{len(results)}) | Avg latency: {avg_lat:.2f}s | Avg payload: {avg_payload:.0f}B | Avg options: {avg_opts:.1f} | Total time: {model_time:.2f}s[/bold]\n"
    )
    return {
        "results": results,
        "accuracy": acc,
        "avg_latency": avg_lat,
        "avg_payload_bytes": avg_payload,
        "avg_num_options": avg_opts,
        "total_time": model_time,
        "correct": correct,
        "total": len(results),
        "mode": mode,
    }


async def main():
    global SYSTEMONE_URL

    pr = _load_private()
    default_url = getattr(pr, "SYSONE_URL", _DEFAULT_SYSTEMONE_URL) if pr else _DEFAULT_SYSTEMONE_URL
    default_model = getattr(pr, "SYSONE_MDL", None) if pr else None
    key = getattr(pr, "SYSONE_KEY", None) if pr else None
    auth_header = {"Authorization": f"Bearer {key}"} if key else {}

    parser = argparse.ArgumentParser(description="Extended intent decoder tests")
    parser.add_argument("--url", default=default_url, help="SystemOne endpoint")
    parser.add_argument("--model", action="append", dest="models", help="model(s) to test (repeatable)")
    parser.add_argument(
        "--modes", default="choice,noul_multi,score,slot",
        help="comma-separated modes: choice,noul_multi,score,slot",
    )
    args = parser.parse_args()

    SYSTEMONE_URL = args.url
    models = args.models or ([default_model] if default_model else _DEFAULT_MODELS)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    run_start = time.time()
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.rule(f"[bold blue]Extended Intent Decoder Tests ({','.join(modes)}) | {run_ts}")

    config = load_config()
    test_cases = generate_test_cases(config)[:10]

    console.print(f"Using {len(test_cases)} test cases")
    console.print(f"Models: {', '.join(models)}")
    console.print(f"Endpoint: {SYSTEMONE_URL}\n")

    all_results = {}
    for model in models:
        all_results[model] = {}
        for mode in modes:
            all_results[model][mode] = await test_model(model, config, test_cases, mode, auth_header)

    for mode in modes:
        table = Table(title=f"Summary - Mode: {mode}")
        table.add_column("Model", style="cyan")
        table.add_column("Accuracy", justify="right")
        table.add_column("Avg Latency", justify="right")
        table.add_column("Avg Payload", justify="right")
        table.add_column("Avg Options", justify="right")
        table.add_column("Correct/Total", justify="right")
        table.add_column("Total Time", justify="right")
        for model in models:
            data = all_results[model][mode]
            table.add_row(
                model,
                f"{data['accuracy']:.1f}%",
                f"{data['avg_latency']:.2f}s",
                f"{data['avg_payload_bytes']:.0f}B",
                f"{data['avg_num_options']:.1f}",
                f"{data['correct']}/{data['total']}",
                f"{data['total_time']:.2f}s",
            )
        console.print(table)
        console.print()

    console.print(f"[bold]Overall runtime: {time.time() - run_start:.2f}s[/bold]")

    results_path = _REPO_ROOT / "results" / f"results_extended_{int(time.time())}.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_data = {
        "timestamp": run_ts,
        "endpoint": SYSTEMONE_URL,
        "models": all_results,
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, ensure_ascii=False, indent=2)
    console.print(f"\n[green]Results saved to {results_path}[/green]")


if __name__ == "__main__":
    asyncio.run(main())
