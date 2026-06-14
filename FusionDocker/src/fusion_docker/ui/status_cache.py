"""Background runtime-status refresher for the dashboard.

Collecting docker/tmux runtime status shells out to ``docker ps`` / ``tmux`` and,
for remote targets, runs commands over SSH. Doing that synchronously inside the
``/api/status`` request (polled every few seconds by every open browser) meant a
single slow SSH probe froze start/stop/logs for everyone, because it ran while
holding the controller lock.

This refresher moves that work onto a single background thread. It periodically
asks the controller to recompute its cached snapshot; request handlers then read
the cached snapshot without blocking on subprocesses.
"""

from __future__ import annotations

from threading import Event, Thread
from typing import Callable

from fusion_docker.console import print_warning


class RuntimeStatusRefresher:
    """Periodically invokes a refresh callback on a daemon thread."""

    def __init__(self, refresh: Callable[[], None], *, interval_s: float = 3.0) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be greater than 0.")
        self._refresh = refresh
        self._interval_s = interval_s
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(
            target=self._run,
            name="ui-status-refresher",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._refresh()
            except Exception as exc:  # pragma: no cover - defensive
                print_warning(f"Status refresh failed: {exc}")
            self._stop.wait(self._interval_s)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            self._thread = None
