"""Console status reporting with a maximum 10s silence interval.

Spec requirement (kg-pair-identification): "The script SHALL print
progress status ... at intervals of at most 10 seconds".

``StatusTicker`` remembers how long ago it last printed and flushes when
the interval has elapsed or ``finish()`` is called. expensive work is
responsible for calling :meth:`ticker.tick` / :meth:`this.record` around
its loops.
"""

from __future__ import annotations

import sys
import time

DEFAULT_INTERVAL = 10.0


class StatusTicker:
    """Prints a status line if at least *interval* seconds have passed."""

    def __init__(self, interval: float = DEFAULT_INTERVAL, stream=None):
        self.interval = interval
        self.stream = stream or sys.stdout
        self._last = time.monotonic()
        self._printed = False
        self._prefix = ""

    def tick(self, message: str = "", force: bool = False) -> bool:
        """Print ``prefix + message`` when the interval has elapsed.

        With ``force=True`` the line prints immediately regardless of the
        interval (use for section starts / final summaries).

        Returns True when a line was printed.
        """
        now = time.monotonic()
        if (now - self._last >= self.interval or force or not self._printed) and (
            message or self._prefix
        ):
            line = f"[{time.strftime('%H:%M:%S')}] {self._prefix}{message}".rstrip()
            print(line, file=self.stream, flush=True)
            self._last = now
            self._printed = True
            return True
        return False

    def section(self, prefix: str) -> None:
        """Set a prefix shown on every subsequent status line."""
        self._prefix = prefix + " " if prefix else ""
        self._last = 0.0 - self.interval  # force the next tick
