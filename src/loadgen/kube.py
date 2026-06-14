from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pandas as pd


class ReplicaSampler:
    def __init__(
        self,
        namespace: str,
        output_csv: Path,
        interval_s: float = 5.0,
        selector: str | None = None,
        kubeconfig: str | None = None,
    ) -> None:
        self.namespace = namespace
        self.output_csv = output_csv
        self.interval_s = interval_s
        self.selector = selector
        self.kubeconfig = kubeconfig
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rows: list[dict[str, float | str]] = []
        self._start_ts = 0.0

    def start(self) -> None:
        self._start_ts = time.time()
        self._thread = threading.Thread(target=self._run, name="replica-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> pd.DataFrame:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_s + 5)
        df = pd.DataFrame(self._rows)
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.output_csv, index=False)
        return df

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self.interval_s)

    def _sample_once(self) -> None:
        now = time.time()
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        cmd.extend(["get", "deployments", "-n", self.namespace, "-o", "json"])
        if self.selector:
            cmd.extend(["-l", self.selector])

        try:
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            data = json.loads(result.stdout)
        except Exception as exc:
            self._rows.append({
                "t_s": now - self._start_ts,
                "t_min": (now - self._start_ts) / 60.0,
                "service": "__sampler_error__",
                "replicas": 0,
                "error": str(exc),
            })
            return

        total = 0
        for item in data.get("items", []):
            name = item.get("metadata", {}).get("name", "unknown")
            replicas = int(item.get("status", {}).get("replicas") or 0)
            total += replicas
            self._rows.append({
                "t_s": now - self._start_ts,
                "t_min": (now - self._start_ts) / 60.0,
                "service": name,
                "replicas": replicas,
                "error": "",
            })

        self._rows.append({
            "t_s": now - self._start_ts,
            "t_min": (now - self._start_ts) / 60.0,
            "service": "__total__",
            "replicas": total,
            "error": "",
        })
