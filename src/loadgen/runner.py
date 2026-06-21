from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .kube import ReplicaSampler
from .locustgen import write_wrapper
from .patterns import format_duration, max_rps, pattern_duration, sample_pattern
from .plots import plot_run, save_ideal_rps_plot


@dataclass(frozen=True)
class ArtifactDirs:
    root: Path
    csv: Path
    generated: Path
    locust: Path
    plots: Path
    preview: Path


def artifact_dirs(run_dir: Path) -> ArtifactDirs:
    return ArtifactDirs(
        root=run_dir,
        csv=run_dir / "csv",
        generated=run_dir / "generated",
        locust=run_dir / "locust",
        plots=run_dir / "plots",
        preview=run_dir / "preview",
    )


def existing_artifact_dir(run_dir: Path, name: str) -> Path:
    candidate = run_dir / name
    return candidate if candidate.exists() else run_dir


def artifact_file(run_dir: Path, name: str, filename: str) -> Path:
    candidate = run_dir / name / filename
    return candidate if candidate.exists() else run_dir / filename


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        if path.suffix.lower() == ".json":
            data = json.load(handle)
        else:
            try:
                import yaml
            except ModuleNotFoundError as exc:
                raise RuntimeError("YAML configs require PyYAML. Install with: pip install -e .") from exc
            data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("config must be a YAML/JSON object")
    return data


def run_experiment(config_path: Path, dry_run: bool = False) -> Path:
    config_path = config_path.resolve()
    cfg = load_config(config_path)
    validate_config(cfg)

    run_dir = experiment_dir(config_path, cfg)
    prepare_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    dirs = artifact_dirs(run_dir)
    for path in [dirs.csv, dirs.generated, dirs.locust, dirs.plots]:
        path.mkdir(parents=True, exist_ok=True)

    pattern = cfg["pattern"]
    ideal_df = sample_pattern(pattern, step_s=float(cfg.get("sample_interval_s", 1.0)))
    ideal_df.to_csv(dirs.csv / "ideal_rps.csv", index=False)
    save_ideal_rps_plot(ideal_df, dirs.plots / "ideal_rps")

    app_locustfile = resolve_path(cfg["locustfile"], config_path.parent)
    wrapper = write_wrapper(app_locustfile, dirs.generated / "locustfile.py")
    shutil.copy2(app_locustfile, dirs.generated / "app_locustfile.py")

    slo_ms = cfg.get("slo_ms")

    if dry_run:
        plot_run(run_dir, slo_ms=slo_ms)
        write_summary(run_dir, dry_run=True, slo_ms=slo_ms)
        return run_dir

    sampler = maybe_start_sampler(cfg, dirs.csv, config_path.parent)
    locust_exit = run_locust(cfg, wrapper, dirs.locust)
    if sampler:
        sampler.stop()

    normalize_locust_history(dirs.locust, dirs.csv, p95_window_s=float(cfg.get("p95_window_s", 30.0)))
    plot_run(run_dir, slo_ms=slo_ms)
    write_summary(run_dir, dry_run=False, locust_exit=locust_exit, slo_ms=slo_ms)

    if locust_exit != 0:
        raise RuntimeError(f"locust exited with status {locust_exit}; artifacts are in {run_dir}")
    return run_dir


def prepare_run_dir(run_dir: Path) -> None:
    for child in ["__pycache__", "csv", "generated", "locust", "plots", "preview"]:
        shutil.rmtree(run_dir / child, ignore_errors=True)
    for child in [
        "actual_rps.csv",
        "actual_rps.png",
        "app_locustfile.py",
        "failed_rps.csv",
        "failed_rps.png",
        "ideal_rps.csv",
        "ideal_rps.png",
        "locust_exceptions.csv",
        "locust_failures.csv",
        "locust_stats.csv",
        "locust_stats_history.csv",
        "locust_stats_stats.csv",
        "locust_stats_history_stats.csv",
        "locust.log",
        "locustfile.py",
        "p95_response_time.csv",
        "p95_response_time.png",
        "preview_ideal_rps.csv",
        "preview_ideal_rps.png",
        "replicas.csv",
        "replicas_by_service.png",
        "successful_rps.csv",
        "successful_rps.png",
        "summary.json",
        "total_replicas.png",
    ]:
        path = run_dir / child
        if path.exists():
            path.unlink()


def experiment_dir(config_path: Path, cfg: dict[str, Any]) -> Path:
    output_root = resolve_path(cfg.get("output_dir", "outputs"), config_path.parent)
    run_name = cfg.get("name") or "experiment"
    if config_path.parent.name == run_name:
        return output_root
    if output_root.name == run_name:
        return output_root
    return output_root / run_name


def validate_config(cfg: dict[str, Any]) -> None:
    required = ["locustfile", "pattern"]
    missing = [name for name in required if name not in cfg]
    if "host" not in cfg and "endpoints" not in cfg:
        missing.append("host or endpoints")
    if missing:
        raise ValueError(f"missing required config keys: {', '.join(missing)}")
    if "endpoints" in cfg:
        normalize_endpoints(cfg["endpoints"], "endpoints")
    validate_pattern_endpoints(cfg["pattern"])
    pattern_duration(cfg["pattern"])


def normalize_endpoints(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty list")
    endpoints: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if isinstance(item, str):
            url = item
            weight = 1.0
        elif isinstance(item, dict):
            url = item.get("url") or item.get("host")
            weight = float(item.get("weight", 1.0))
        else:
            raise ValueError(f"{item_path} must be a URL string or object")
        if not url or not isinstance(url, str):
            raise ValueError(f"{item_path}.url is required")
        if weight <= 0:
            raise ValueError(f"{item_path}.weight must be greater than 0")
        endpoints.append({"url": url.rstrip("/"), "weight": weight})
    return endpoints


def validate_pattern_endpoints(pattern: dict[str, Any], path: str = "pattern") -> None:
    if "endpoints" in pattern:
        normalize_endpoints(pattern["endpoints"], f"{path}.endpoints")
    if pattern.get("type") == "mixed":
        for index, part in enumerate(pattern.get("parts", [])):
            validate_pattern_endpoints(part, f"{path}.parts[{index}]")


def resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def maybe_start_sampler(cfg: dict[str, Any], csv_dir: Path, config_dir: Path) -> ReplicaSampler | None:
    kube_cfg = cfg.get("kubernetes") or {}
    if not kube_cfg.get("enabled", False):
        return None

    namespace = kube_cfg.get("namespace")
    if not namespace:
        raise ValueError("kubernetes.namespace is required when kubernetes.enabled is true")

    sampler = ReplicaSampler(
        namespace=namespace,
        output_csv=csv_dir / "replicas.csv",
        interval_s=float(kube_cfg.get("sample_interval_s", 5.0)),
        selector=kube_cfg.get("selector"),
        kubeconfig=str(resolve_path(kube_cfg["kubeconfig"], config_dir))
        if kube_cfg.get("kubeconfig")
        else None,
    )
    sampler.start()
    return sampler


def run_locust(cfg: dict[str, Any], wrapper: Path, locust_dir: Path) -> int:
    pattern = cfg["pattern"]
    endpoint_config = cfg["endpoints"] if "endpoints" in cfg else [cfg["host"]]
    endpoints = normalize_endpoints(endpoint_config, "endpoints")
    locust_host = cfg.get("host") or endpoints[0]["url"]
    max_users = max(1, int(math.ceil(float(cfg.get("max_users", max_rps(pattern))))))
    spawn_rate = float(cfg.get("spawn_rate", min(max_users, 100)))
    run_time = format_duration(pattern_duration(pattern))
    csv_prefix = locust_dir / "locust"

    cmd = [
        "locust",
        "-f",
        str(wrapper),
        "--headless",
        "--host",
        str(locust_host),
        "--run-time",
        run_time,
        "--csv",
        str(csv_prefix),
        "--csv-full-history",
        "--exit-code-on-error",
        str(int(cfg.get("exit_code_on_error", 0))),
        "-u",
        str(max_users),
        "-r",
        str(spawn_rate),
    ]
    if cfg.get("locust_args"):
        cmd.extend(str(arg) for arg in cfg["locust_args"])

    env = os.environ.copy()
    env["LOADGEN_PATTERN_JSON"] = json.dumps(pattern)
    env["LOADGEN_ENDPOINTS_JSON"] = json.dumps(endpoints)
    env["LOADGEN_SPAWN_RATE"] = str(spawn_rate)

    log_path = locust_dir / "locust.log"
    print("[load-gen] running:", " ".join(cmd))
    print(f"[load-gen] locust output: {log_path}")
    if cfg.get("stream_locust_output", False):
        proc = subprocess.run(cmd, env=env)
    else:
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc.returncode


def normalize_locust_history(locust_dir: Path, csv_dir: Path, p95_window_s: float = 30.0) -> None:
    history_path = locust_dir / "locust_stats_history.csv"
    if not history_path.exists():
        print(f"[load-gen] missing Locust history CSV: {history_path}", file=sys.stderr)
        return

    history = pd.read_csv(history_path)
    if history.empty:
        return

    total = select_total_history(history)
    if total.empty:
        return

    t0 = pd.to_datetime(total["Timestamp"], unit="s", errors="coerce")
    if t0.notna().any():
        start = t0.dropna().iloc[0]
        total["t_s"] = (t0 - start).dt.total_seconds()
    else:
        print("WARNING: Locust Timestamp column missing or malformed; falling back to row-index time", flush=True)
        total["t_s"] = range(len(total))
    total["t_min"] = total["t_s"] / 60.0

    actual_rps_col = first_existing(total, ["Requests/s", "Total RPS", "Current RPS"])
    failed_rps_col = first_existing(total, ["Failures/s", "Total Failure RPS", "Current Failures/s"])
    p95_col = first_existing(total, ["95%", "95%ile", "p95"])

    if actual_rps_col:
        rates = total[["t_s", "t_min", actual_rps_col]].rename(columns={actual_rps_col: "actual_rps"})
        rates["actual_rps"] = pd.to_numeric(rates["actual_rps"], errors="coerce")
        rates.to_csv(csv_dir / "actual_rps.csv", index=False)

        if failed_rps_col:
            rates["failed_rps"] = pd.to_numeric(total[failed_rps_col], errors="coerce")
            rates[["t_s", "t_min", "failed_rps"]].to_csv(csv_dir / "failed_rps.csv", index=False)
            rates["successful_rps"] = (rates["actual_rps"] - rates["failed_rps"]).clip(lower=0)
            rates[["t_s", "t_min", "successful_rps"]].to_csv(
                csv_dir / "successful_rps.csv", index=False
            )
    if p95_col:
        p95 = total[["t_s", "t_min", p95_col]].copy()
        p95[p95_col] = pd.to_numeric(p95[p95_col], errors="coerce")
        p95 = p95.dropna(subset=[p95_col])
        if p95_window_s > 0 and not p95.empty:
            p95["window_index"] = (p95["t_s"] // p95_window_s).astype(int)
            p95 = (
                p95.groupby("window_index", as_index=False)
                .agg(t_s=("t_s", "max"), t_min=("t_min", "max"), p95_ms=(p95_col, "mean"))
                .drop(columns=["window_index"])
            )
            p95["window_s"] = float(p95_window_s)
        else:
            p95 = p95.rename(columns={p95_col: "p95_ms"})
        p95.to_csv(csv_dir / "p95_response_time.csv", index=False)

def select_total_history(history: pd.DataFrame) -> pd.DataFrame:
    if "Name" not in history.columns:
        return history.copy()
    total = history[history["Name"].astype(str).str.lower() == "aggregated"].copy()
    if total.empty:
        total = history[history["Name"].astype(str).str.lower() == "total"].copy()
    if total.empty:
        total = history.copy()
    return total.reset_index(drop=True)


def first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def write_summary(run_dir: Path, dry_run: bool, locust_exit: int | None = None, slo_ms: float | None = None) -> None:
    csv_dir = existing_artifact_dir(run_dir, "csv")
    locust_dir = existing_artifact_dir(run_dir, "locust")
    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "csv_dir": str(csv_dir),
        "locust_dir": str(locust_dir),
        "plots_dir": str(run_dir / "plots"),
        "dry_run": dry_run,
        "locust_exit": locust_exit,
    }

    for metric, filename, column in [
        ("ideal_rps", "ideal_rps.csv", "ideal_rps"),
        ("actual_rps", "actual_rps.csv", "actual_rps"),
        ("failed_rps", "failed_rps.csv", "failed_rps"),
        ("successful_rps", "successful_rps.csv", "successful_rps"),
    ]:
        path = artifact_file(run_dir, "csv", filename)
        if path.exists():
            df = pd.read_csv(path)
            if column in df and not df.empty:
                summary[metric] = {
                    "mean": float(df[column].mean()),
                    "max": float(df[column].max()),
                    "last": float(df[column].iloc[-1]),
                }

    response_time = response_time_summary(run_dir, slo_ms=slo_ms)
    if response_time:
        summary["response_time_ms"] = response_time

    replicas = artifact_file(run_dir, "csv", "replicas.csv")
    if replicas.exists():
        df = pd.read_csv(replicas)
        total = df[df["service"] == "__total__"] if "service" in df else pd.DataFrame()
        if not total.empty:
            summary["total_replicas"] = {
                "mean": float(total["replicas"].mean()),
                "max": float(total["replicas"].max()),
                "last": float(total["replicas"].iloc[-1]),
            }

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def response_time_summary(run_dir: Path, slo_ms: float | None = None) -> dict[str, float] | None:
    summary: dict[str, float] = {}

    stats_path = artifact_file(run_dir, "locust", "locust_stats.csv")
    if stats_path.exists():
        stats = pd.read_csv(stats_path)
        total = select_total_history(stats)
        p95_col = first_existing(total, ["95%", "95%ile", "p95"])
        if p95_col and not total.empty:
            values = pd.to_numeric(total[p95_col], errors="coerce").dropna()
            if not values.empty:
                summary["p95_overall"] = float(values.iloc[-1])

    p95_path = artifact_file(run_dir, "csv", "p95_response_time.csv")
    if p95_path.exists():
        p95 = pd.read_csv(p95_path)
        if "p95_ms" in p95 and not p95.empty:
            values = pd.to_numeric(p95["p95_ms"], errors="coerce").dropna()
            if not values.empty:
                if "window_s" in p95:
                    window_values = pd.to_numeric(p95["window_s"], errors="coerce").dropna()
                    if not window_values.empty:
                        summary["p95_window_s"] = float(window_values.iloc[-1])
                summary["p95_window_mean"] = float(values.mean())
                summary["p95_window_max"] = float(values.max())
                summary["p95_window_last"] = float(values.iloc[-1])
                if slo_ms is not None:
                    violations = int((values > slo_ms).sum())
                    total_windows = len(values)
                    summary["slo_ms"] = float(slo_ms)
                    summary["slo_violation_windows"] = violations
                    summary["slo_compliance_pct"] = round(
                        100.0 * (total_windows - violations) / total_windows, 2
                    )

    return summary or None
