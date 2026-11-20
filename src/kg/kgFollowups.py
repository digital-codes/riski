"""kgFollowups — backends-sealed conversation state + follow-up questions.

Implements tasks 5.1–5.3 of change `kg-app-integration`: the auenBot
state-token pattern (AES-GCM sealed sessions, session-bound AAD) ported
from `botCtl/botQa.seal_state`/`open_state`:

* `seal_state(state, session_id)` — state dict → opaque `v1.<b64url>` token
  (key = HMAC-SHA256 over `STATE_TOKEN_SECRET` + session id; `_ts` sealed
   for expiry; tampered / foreign-session tokens reject on open).
* `open_state(token, session_id)` — reverse; raises ValueError on
   expiry/unsupported version/malformed payload
  (InvalidTag → caller maps to 400).
* `generate_followups(answer, statements, topics, session_id, max_n=5)` —
  3–5 German follow-up questions via the CCLLM route (fallback: generic
  cloud chat), grounded in the answer + statement facts + kg topics.
* `followup_answer(...)` helper — a follow-up turn reuses the sealed
  payload'soparl keys as grounding context (never trusting the token
  content as fact source — re-reads statements from kg_*)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVER_SECRET: bytes | None = (
    os.environ["STATE_TOKEN_SECRET"].encode("utf-8")
    if os.environ.get("STATE_TOKEN_SECRET") is not None
    else None  # fallback: random ephemeral (tokens die on restart)
)

STATE_TOKEN_MAX_AGE = int(
    os.environ.get("STATE_TOKEN_MAX_AGE", str(7 * 24 * 3600))
)

_SESSION_RE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

if SERVER_SECRET is None:
    SERVER_SECRET = os.urandom(32)
    
import sys  # noqa: E402
if os.environ.get("STATE_TOKEN_SECRET") is None:
    print("Warning: STATE_TOKEN_SECRET not set — tokens are ephemeral",
          file=sys.stderr)


def _derive_key(session_id: str, secret: bytes) -> bytes:
    return hmac.new(secret, session_id.encode("utf-8"), hashlib.sha256).digest()


def seal_state(state: dict[str, Any], session_id: str, *,
               secret: bytes | None = None) -> str:
    """State dict → opaque sealed token (auenBot v1 format)."""
    key = _derive_key(session_id, secret or SERVER_SECRET)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    payload = dict(state)
    payload["_ts"] = int(time.time())
    plaintext = json.dumps(payload, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    blob = nonce + aesgcm.encrypt(nonce, plaintext, session_id.encode("utf-8"))
    token = base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")
    return f"v1.{token}"


def open_state(token: str, session_id: str, *,
               secret: bytes | None = None) -> dict[str, Any]:
    """Sealed token → state dict. Raises ValueError / InvalidTag."""
    if not token.startswith("v1."):
        raise ValueError("Unsupported state token version")
    b64 = token[3:]
    pad = "=" * (-len(b64) % 4)
    blob = base64.urlsafe_b64decode(b64 + pad)
    nonce, ciphertext = blob[:12], blob[12:]
    key = _derive_key(session_id, secret or SERVER_SECRET)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, session_id.encode("utf-8"))
    data = json.loads(plaintext.decode("utf-8"))
    ts = data.pop("_ts", None)
    if ts is not None and STATE_TOKEN_MAX_AGE > 0:
        if int(time.time()) - ts > STATE_TOKEN_MAX_AGE:
            raise ValueError("State token expired")
    return data


def seal_state_or_none(state: dict[str, Any], session_id: str) -> str | None:
    """Best-effort sealing — None when a malformed session id appears."""
    if not session_id or any(c not in _SESSION_RE_CHARS for c in session_id):
        return None
    try:
        return seal_state(state, session_id)
    except Exception:  # pragma: no cover
        return None


# ---------------------------------------------------------------------
# follow-up question generation
# ---------------------------------------------------------------------

FOLLOWUP_PROMPT = """Du bist ein Assistent für das Ratsinformationssystem
Karlsruhe. Aus dem folgenden Antworttext und den extrahierten Fakten und
kg-topics (Themen) nenne 3–5 gezielte follow-up-Fragen, die ein Nutzer
als Follow-up auf diese Antwort stellen könnte. Berücksichtige
verschiedene Aspekte: Ergebnis/Umsetzung, Kosten, betroffene Orte,
verwandte Themen (kg-topics), Zeitplan. Antworte NUR mit einem
JSON-Objekt: {{"questions": ["Frage 1", "Frage 2", ...]}} mit
höchstens 5 Fragen. Deutsch."""

FOLLOWUP_MAX = 5
FOLLOWUP_MIN = 3


def generate_followups(answer_summary: str, statements: list[dict] | None,
                       topics: list[str] | None, *, model: str | None = None,
                       remote: Any = None) -> dict[str, Any]:
    """LLM-generate follow-ups; returns {questions, topics, generation}. """
    from src.remote import chat as remote_chat
    stmt_bits = json.dumps(statements or [], ensure_ascii=False)[:2000]
    topics_bits = ", ".join(topics or [])
    user = (f"Antwort:\n{answer_summary[:6000]}\n\n"
            f"Extrahierte Fakten:\n{stmt_bits[:2000]}\n\n"
            f"kg-topics: {topics_bits}")
    chat = remote.chat_json if remote else None
    if chat is not None:
        client = remote
    else:
        from src.kg.kgRemote import KgRemote
        client = KgRemote.for_diagnose() or KgRemote("olc")
    raw = client.chat([{"role": "system", "content": FOLLOWUP_PROMPT},
                       {"role": "user", "content": user}],
                      model=model or "glm-5.3-flash:cloud")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise
        data = json.loads(m.group(0))
    questions = [q for q in (data.get("questions") or []) if q][:FOLLOWUP_MAX]
    return {"questions": questions, "topics": topics or [],
            "generation": "kg-followups"}


def followup_turn(payload: dict, session_id: str, question: str) -> dict[str, Any]:
    """Scope the follow-up turn: opens the sealed state, returns the
    grounding context aspects (oparl keys + pair ids to re-derive)."""
    state = open_state(payload, session_id)
    return {
        "original_query": state.get("q0"),
        "top_docs": state.get("top_docs") or [],
        "statement_refs": state.get("stmt_refs") or [],
        "topics": state.get("topics") or [],
        "question": question,
    }
