"""Lightweight execution-time measurement (stdlib only).

- ``@timed`` — decorator printing wall time per call:
      @timed
      def search_and_build_timeline(...): ...
      @timed(label="rerank")
      def call_reranking_model(...): ...

- ``timed_block("label")`` — context manager for sub-blocks:
      with timed_block("hybrid.lexical"):
          ...

Output goes to the ``riski.timing`` logger as ``[timing] <label>:
<seconds>s``. Instrumentation is OFF by default (production servers stay
quiet); enable with ``RISKI_TIMING=1`` (also: true/yes/on). For deeper
analysis the stdlib's cProfile stays available.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import functools
import logging
import os
import time
from contextlib import contextmanager

_TRUTHY_ON = {"1", "true", "yes", "on"}

logger = logging.getLogger("riski.timing")


def enabled() -> bool:
    """Whether timing output is on (env ``RISKI_TIMING``, default: off)."""
    return os.getenv("RISKI_TIMING", "0").strip().lower() in _TRUTHY_ON


def _ensure_handler() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # stay independent of root-logger config


def _report(label: str, seconds: float) -> None:
    if enabled():
        _ensure_handler()
        logger.info("[timing] %s: %.3fs", label, seconds)


def timed(func=None, *, label: str | None = None):
    """Decorator measuring wall-clock execution time of a function."""
    def decorate(fn):
        name = label or f"{fn.__module__.split('.')[-1]}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                _report(name, time.perf_counter() - t0)
        return wrapper

    if func is not None:  # used bare: @timed
        return decorate(func)
    return decorate  # used with arguments: @timed(label="...")


@contextmanager
def timed_block(label: str):
    """Context manager measuring a code block."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _report(label, time.perf_counter() - t0)
