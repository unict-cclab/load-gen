from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any


class LiveProgress:
    """Live terminal progress display during a Locust run.

    No-op when stdout is not a TTY or when rich is not installed.
    """

    def __init__(
        self,
        *,
        total_s: float,
        warmup_s: float,
        stats_path: Path,
        name: str,
    ) -> None:
        self._total_s = total_s
        self._warmup_s = warmup_s
        self._stats_path = stats_path
        self._name = name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._progress: Any = None
        self._task_id: Any = None
        self._start: float = 0.0
        self._enabled: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def __enter__(self) -> "LiveProgress":
        if not self._enabled:
            return self
        try:
            from rich.console import Console
            from rich.progress import (
                BarColumn,
                Progress,
                TaskProgressColumn,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )

            console = Console(stderr=True, highlight=False)
            self._progress = Progress(
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("eta"),
                TimeRemainingColumn(),
                TextColumn("  {task.fields[metrics]}"),
                console=console,
            )
            self._task_id = self._progress.add_task(
                self._name, total=self._total_s, metrics="[dim]—[/dim]"
            )
            self._start = time.monotonic()
            self._progress.__enter__()
            self._thread = threading.Thread(
                target=self._poll, daemon=True, name="loadgen-progress"
            )
            self._thread.start()
        except Exception:
            self._enabled = False
        return self

    def __exit__(self, *args: Any) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        if self._progress is not None:
            if self._task_id is not None:
                self._progress.update(self._task_id, completed=self._total_s)
            self._progress.__exit__(*args)

    def _poll(self) -> None:
        while not self._stop.wait(1.0):
            elapsed = time.monotonic() - self._start
            if self._progress is not None and self._task_id is not None:
                self._progress.update(
                    self._task_id,
                    completed=min(elapsed, self._total_s),
                    metrics=self._read_metrics(elapsed),
                )

    def _read_metrics(self, elapsed: float) -> str:
        if not self._stats_path.exists():
            return "[dim]—[/dim]"
        try:
            import pandas as pd

            df = pd.read_csv(self._stats_path)
            if df.empty:
                return "[dim]—[/dim]"
            if "Name" in df.columns:
                agg = df[df["Name"].str.lower() == "aggregated"]
                if agg.empty:
                    agg = df[df["Name"].str.lower() == "total"]
                if agg.empty:
                    agg = df.tail(1)
            else:
                agg = df.tail(1)
            if agg.empty:
                return "[dim]—[/dim]"
            r = agg.iloc[-1]

            parts: list[str] = []

            rps_col = _first(r, ["Requests/s", "Total RPS", "Current RPS"])
            rps_val = _float(r[rps_col]) if rps_col else 0.0
            if rps_col:
                parts.append(f"rps [bold]{rps_val:.1f}[/bold]")

            p95_col = _first(r, ["95%", "95%ile", "p95"])
            if p95_col:
                p95 = _float(r[p95_col])
                if p95 > 500:
                    parts.append(f"p95 [bold red]{p95:.0f}ms[/bold red]")
                elif p95 > 200:
                    parts.append(f"p95 [bold yellow]{p95:.0f}ms[/bold yellow]")
                else:
                    parts.append(f"p95 [bold]{p95:.0f}ms[/bold]")

            fail_col = _first(r, ["Failures/s", "Total Failure RPS", "Current Failures/s"])
            if fail_col:
                fail = _float(r[fail_col])
                pct = 100.0 * fail / rps_val if rps_val > 0 else 0.0
                if pct > 1:
                    parts.append(f"err [bold red]{pct:.1f}%[/bold red]")
                elif pct > 0:
                    parts.append(f"err [bold yellow]{pct:.1f}%[/bold yellow]")
                else:
                    parts.append(f"err [bold]{pct:.1f}%[/bold]")

            user_col = _first(r, ["User count", "Users"])
            if user_col:
                users = int(_float(r[user_col]))
                parts.append(f"users [bold]{users}[/bold]")

            if self._warmup_s > 0:
                if elapsed < self._warmup_s:
                    parts.append("[dim yellow]warmup[/dim yellow]")
                else:
                    parts.append("[dim green]run[/dim green]")

            return "  ".join(parts) if parts else "[dim]—[/dim]"
        except Exception:
            return "[dim]—[/dim]"


def _first(row: Any, names: list[str]) -> str | None:
    for n in names:
        if n in row.index:
            return n
    return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
