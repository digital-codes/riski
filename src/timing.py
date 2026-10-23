"""Lightweight execution-time measurement (stdlib only).

- ``@timed`` — decorator printing wall time per call:
      @timed
      def search_and_build_timeline(...): ...
      @timed(label="rerank")
      def call_reranking_model(...): ...

- ``timed_block("label")`` — context manager for sub-blocks:
      with timed_block("hybrid.lexical"):
          ...

Output goes to stdout as ``[timing] <label>: <seconds>s`` (the codebase
logs via print). For deeper analysis the stdlib's cProfile stays available.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import functools
import time
from contextlib import contextmanager


def _report(label: str, seconds: float) -> None:
    print(f"[timing] {label}: {seconds:.3f}s")


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
