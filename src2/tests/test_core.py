'''Unit tests for the unified `src2` utilities.

These tests run against the defaults defined in `src/private.py`:
* PostgreSQL on `localhost` with user/password `riski`
* Chat endpoint `http://localhost:8080/v1` using model `granite-4.1-3b-Q8_0`
* Embedding endpoint `http://localhost:8085/v1` using model `bge-m3-Q4_K_M`
'''

import pytest
import numpy as np

from src2 import db, remote

def test_engine_connection():
    """Validate that the shared engine can connect to the DB."""
    engine = db.get_engine()
    with engine.connect() as conn:
        result = conn.execute(db.text("SELECT 1"))
        assert result.scalar() == 1

def test_embed_returns_normalised_vector():
    vec = remote.embed("unit test text")
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (remote.EMBED_DIM,)
    norm = np.linalg.norm(vec)
    assert pytest.approx(norm, rel=1e-3) == 1.0

def test_chat_returns_response_dict():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello"},
    ]
    resp = remote.chat(messages)
    # Should be a dict with content and optional token usage fields
    assert isinstance(resp, dict)
    assert "content" in resp
    assert isinstance(resp["content"], str)
    # Token fields may be None if the backend does not provide them
    for key in ["prompt_tokens", "completion_tokens", "total_tokens"]:
        assert key in resp
        # Values are either int or None
        assert resp[key] is None or isinstance(resp[key], int)
    assert len(resp["content"].strip()) > 0

def test_chat_thinking_mode_enabled():
    messages = [
        {"role": "user", "content": "Explain the meaning of life in 20 words."},
    ]
    # Thinking disabled (default) – get response
    resp_no_think = remote.chat(messages, thinking=False)
    # Thinking enabled – should still succeed and return dict with same keys
    resp_think = remote.chat(messages, thinking=True)
    assert isinstance(resp_think, dict)
    assert "content" in resp_think
    # Ensure the content strings are non‑empty
    assert len(resp_no_think["content"].strip()) > 0
    assert len(resp_think["content"].strip()) > 0
