from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd


SCHEDULING_COLUMNS = [
    "t_s",
    "t_min",
    "pod",
    "uid",
    "service",
    "scheduler",
    "node",
    "phase",
    "created_at",
    "scheduled_at",
    "scheduled",
    "scheduling_duration_s",
    "error",
]


class ReplicaSampler:
    def __init__(
        self,
        namespace: str,
        output_csv: Path,
        scheduling_output_csv: Path | None = None,
        interval_s: float = 5.0,
        selector: str | None = None,
        kubeconfig: str | None = None,
    ) -> None:
        self.namespace = namespace
        self.output_csv = output_csv
        self.scheduling_output_csv = scheduling_output_csv or output_csv.with_name("scheduling.csv")
        self.interval_s = interval_s
        self.selector = selector
        self.kubeconfig = kubeconfig
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rows: list[dict[str, float | str]] = []
        self._pod_rows: dict[str, dict[str, float | str | bool]] = {}
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
        scheduling = pd.DataFrame(self._pod_rows.values(), columns=SCHEDULING_COLUMNS)
        self.scheduling_output_csv.parent.mkdir(parents=True, exist_ok=True)
        scheduling.to_csv(self.scheduling_output_csv, index=False)
        return df

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self.interval_s)

    def _sample_once(self) -> None:
        now = time.time()
        self._sample_deployments(now)
        self._sample_pods(now)

    def _base_kubectl(self) -> list[str]:
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        return cmd

    def _sample_deployments(self, now: float) -> None:
        cmd = self._base_kubectl()
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

    def _sample_pods(self, now: float) -> None:
        cmd = self._base_kubectl()
        cmd.extend(["get", "pods", "-n", self.namespace, "-o", "json"])
        if self.selector:
            cmd.extend(["-l", self.selector])

        try:
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            data = json.loads(result.stdout)
        except Exception as exc:
            key = f"__sampler_error__:{now}"
            self._pod_rows[key] = {
                "t_s": now - self._start_ts,
                "t_min": (now - self._start_ts) / 60.0,
                "pod": "__sampler_error__",
                "uid": key,
                "service": "",
                "scheduler": "",
                "node": "",
                "phase": "",
                "created_at": "",
                "scheduled_at": "",
                "scheduled": False,
                "scheduling_duration_s": "",
                "error": str(exc),
            }
            return

        self._record_pods(data, now)

    def _record_pods(self, data: dict, now: float) -> None:
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})
            labels = metadata.get("labels", {}) or {}
            uid = metadata.get("uid") or metadata.get("name", "unknown")
            created_at = metadata.get("creationTimestamp", "")
            scheduled_at = pod_scheduled_at(status)
            duration_s = scheduling_duration_seconds(created_at, scheduled_at)
            row: dict[str, float | str | bool] = {
                "t_s": now - self._start_ts,
                "t_min": (now - self._start_ts) / 60.0,
                "pod": metadata.get("name", "unknown"),
                "uid": uid,
                "service": labels.get("app") or labels.get("app.kubernetes.io/name") or "",
                "scheduler": spec.get("schedulerName", ""),
                "node": spec.get("nodeName", ""),
                "phase": status.get("phase", ""),
                "created_at": created_at,
                "scheduled_at": scheduled_at,
                "scheduled": bool(scheduled_at),
                "scheduling_duration_s": duration_s if duration_s is not None else "",
                "error": "",
            }
            previous = self._pod_rows.get(uid)
            if previous and previous.get("scheduled_at") and not scheduled_at:
                row["scheduled_at"] = previous["scheduled_at"]
                row["scheduled"] = previous["scheduled"]
                row["scheduling_duration_s"] = previous["scheduling_duration_s"]
            self._pod_rows[uid] = row


def pod_scheduled_at(status: dict) -> str:
    for condition in status.get("conditions", []) or []:
        if condition.get("type") == "PodScheduled" and condition.get("status") == "True":
            return condition.get("lastTransitionTime", "")
    return ""


def scheduling_duration_seconds(created_at: str, scheduled_at: str) -> float | None:
    created = parse_kubernetes_timestamp(created_at)
    scheduled = parse_kubernetes_timestamp(scheduled_at)
    if created is None or scheduled is None:
        return None
    return max(0.0, (scheduled - created).total_seconds())


def parse_kubernetes_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
