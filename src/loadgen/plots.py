from __future__ import annotations

import math
import os
import json
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/loadgen-matplotlib")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FixedLocator


# Keep Matplotlib's familiar default blue for single-series plots. The
# remaining colors are selected for contrast and are reinforced by line styles
# and markers in multi-series plots.
PAPER_COLORS = ["#1F77B4", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]
PAPER_LINESTYLES = ["-", "--", "-.", ":"]
PAPER_MARKERS = ["o", "s", "^", "D", "v", "P", "X"]

PAPER_STYLE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 7.5,
    "axes.labelsize": 7.5,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6,
    "figure.figsize": (3.5, 2.625),
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.facecolor": "white",
    "axes.grid": False,
    "grid.color": "0.86",
    "grid.linewidth": 0.4,
    "grid.alpha": 0.8,
    "axes.spines.top": True,
    "axes.spines.right": True,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.0,
    "legend.frameon": True,
    "legend.framealpha": 0.8,
    "legend.handlelength": 2.2,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}

CONFIGURED_INPUT_LABEL = "Input rate (req/s)"
REQUEST_THROUGHPUT_LABEL = "Throughput (req/s)"
FAILED_THROUGHPUT_LABEL = "Failed requests (req/s)"
REPLICA_COUNT_LABEL = "Replica count"


def apply_style() -> None:
    plt.rcParams.update(PAPER_STYLE)


def set_nice_axis_scale(ax, axis: str, maximum: float, integer: bool = False) -> None:
    if not math.isfinite(maximum) or maximum <= 0:
        maximum = 1
    raw_step = maximum / 5
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized_step = raw_step / magnitude
    candidates = (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)
    step = next(candidate for candidate in candidates if candidate >= normalized_step * 0.98) * magnitude
    if integer:
        step = max(1, math.ceil(step))
    ticks = [index * step for index in range(6)]
    upper = max(ticks[-1], maximum)
    if axis == "y" and math.isclose(upper, maximum, rel_tol=0.001):
        upper += step * 0.25
    locator = FixedLocator(ticks)
    if axis == "x":
        ax.set_xlim(0, upper)
        ax.xaxis.set_major_locator(locator)
    else:
        ax.set_ylim(0, upper)
        ax.yaxis.set_major_locator(locator)


def save_line_plot(
    df: pd.DataFrame,
    output_base: Path,
    x_col: str,
    y_col: str,
    y_label: str,
    series_col: str | None = None,
    hline: float | None = None,
    hline_label: str | None = None,
    legend_outside: bool = False,
    legend_ncol: int | None = None,
    figsize: tuple[float, float] | None = None,
    integer_y: bool = False,
    x_right_padding_fraction: float = 0.0,
) -> None:
    if df.empty:
        return

    apply_style()
    fig, ax = plt.subplots(figsize=figsize)

    if series_col:
        for index, (label, group) in enumerate(df.groupby(series_col)):
            marker_interval = max(1, len(group) // 12)
            ax.plot(
                group[x_col],
                group[y_col],
                color=PAPER_COLORS[index % len(PAPER_COLORS)],
                linestyle=PAPER_LINESTYLES[(index // len(PAPER_COLORS)) % len(PAPER_LINESTYLES)],
                marker=PAPER_MARKERS[index % len(PAPER_MARKERS)],
                markersize=2.4,
                markeredgewidth=0,
                markevery=marker_interval,
                label=str(label),
            )
        if legend_outside:
            ax.legend(
                loc="upper center",
                bbox_to_anchor=(0.5, -0.3),
                ncol=legend_ncol or min(4, df[series_col].nunique()),
                columnspacing=1.0,
                handletextpad=0.4,
            )
        else:
            ax.legend()
    else:
        ax.plot(df[x_col], df[y_col], color=PAPER_COLORS[0])

    if hline is not None:
        ax.axhline(hline, color=PAPER_COLORS[1], linestyle="--", linewidth=0.8, label=hline_label)
        if hline_label:
            ax.legend(loc="best")

    ax.set_xlabel("Time (min)")
    ax.set_ylabel(y_label)
    x_max = float(pd.to_numeric(df[x_col], errors="coerce").max())
    y_max = float(pd.to_numeric(df[y_col], errors="coerce").max())
    if hline is not None:
        y_max = max(y_max, hline)
    set_nice_axis_scale(ax, "x", x_max)
    if x_right_padding_fraction > 0 and x_max > 0:
        left, right = ax.get_xlim()
        ax.set_xlim(left, max(right, x_max * (1 + x_right_padding_fraction)))
    set_nice_axis_scale(ax, "y", y_max, integer=integer_y)
    ax.tick_params(width=0.8, length=3.5, pad=2)
    fig.tight_layout(pad=0.5)

    output_base.parent.mkdir(parents=True, exist_ok=True)
    for suffix in [".pdf", ".png"]:
        fig.savefig(output_base.with_suffix(suffix))
    plt.close(fig)


def save_ideal_rps_plot(df: pd.DataFrame, output_base: Path) -> None:
    save_line_plot(df, output_base, "t_min", "ideal_rps", CONFIGURED_INPUT_LABEL)


def p95_response_time_label(df: pd.DataFrame) -> str:
    return "P95 response time (ms)"


def plot_run(run_dir: Path, slo_ms: float | None = None, output_dir: Path | None = None) -> Path:
    csv_dir = run_dir / "csv"
    plot_dir = output_dir or (run_dir / "plots")
    for legacy_name in ("actual_rps", "successful_rps"):
        for suffix in (".png", ".pdf"):
            (plot_dir / f"{legacy_name}{suffix}").unlink(missing_ok=True)
    for derived_name in ("replicas_by_service", "total_replicas"):
        for suffix in (".png", ".pdf"):
            (plot_dir / f"{derived_name}{suffix}").unlink(missing_ok=True)
        (csv_dir / f"{derived_name}.csv").unlink(missing_ok=True)

    planned = read_run_csv(csv_dir, run_dir, "ideal_rps.csv")
    save_ideal_rps_plot(planned, plot_dir / "ideal_rps")

    throughput = read_run_csv(csv_dir, run_dir, "throughput_rps.csv")
    save_line_plot(throughput, plot_dir / "throughput_rps", "t_min", "throughput_rps", REQUEST_THROUGHPUT_LABEL)

    failures = read_run_csv(csv_dir, run_dir, "failed_rps.csv")
    save_line_plot(failures, plot_dir / "failed_rps", "t_min", "failed_rps", FAILED_THROUGHPUT_LABEL)

    p95 = read_run_csv(csv_dir, run_dir, "p95_response_time.csv")
    save_line_plot(
        p95,
        plot_dir / "p95_response_time",
        "t_min",
        "p95_ms",
        p95_response_time_label(p95),
        hline=slo_ms,
        hline_label=f"SLO ({slo_ms:g} ms)" if slo_ms is not None else None,
    )

    replicas = read_run_csv(csv_dir, run_dir, "replicas.csv")
    if not replicas.empty:
        per_service = replicas[~replicas["service"].astype(str).str.startswith("__")].copy()
        total = replicas[replicas["service"] == "__total__"].copy()
        if not per_service.empty:
            per_service["service_label"] = per_service["service"].map(compact_service_label)
            per_service[["t_min", "service_label", "replicas"]].to_csv(
                csv_dir / "replicas_by_service.csv", index=False
            )
        if not total.empty:
            total[["t_min", "replicas"]].to_csv(csv_dir / "total_replicas.csv", index=False)
        save_line_plot(
            per_service,
            plot_dir / "replicas_by_service",
            "t_min",
            "replicas",
            REPLICA_COUNT_LABEL,
            "service_label",
            legend_outside=True,
            legend_ncol=4,
            figsize=(3.5, 2.625),
            integer_y=True,
            x_right_padding_fraction=0.03,
        )
        save_line_plot(
            total,
            plot_dir / "total_replicas",
            "t_min",
            "replicas",
            REPLICA_COUNT_LABEL,
            integer_y=True,
        )

    return plot_dir


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def read_run_csv(csv_dir: Path, run_dir: Path, filename: str) -> pd.DataFrame:
    path = csv_dir / filename
    if path.exists():
        return read_csv(path)
    return read_csv(run_dir / filename)


def compact_service_label(name: str) -> str:
    label = str(name)
    return label.removesuffix("service")


COMPARISON_METRICS = [
    ("ideal_rps.csv", "ideal_rps", "ideal_rps", CONFIGURED_INPUT_LABEL),
    ("throughput_rps.csv", "throughput_rps", "throughput_rps", REQUEST_THROUGHPUT_LABEL),
    ("failed_rps.csv", "failed_rps", "failed_rps", FAILED_THROUGHPUT_LABEL),
    ("p95_response_time.csv", "p95_ms", "p95_response_time", "P95 response time (ms)"),
]


def aggregate_experiment(experiment_dir: Path) -> None:
    """Create canonical Load Gen plots for the mean time series across runs."""
    csv_output = experiment_dir / "csv"
    plots_output = experiment_dir / "plots"
    csv_output.mkdir(parents=True, exist_ok=True)
    plots_output.mkdir(parents=True, exist_ok=True)
    for legacy_name in ("actual_rps", "successful_rps"):
        for suffix in (".png", ".pdf"):
            (plots_output / f"{legacy_name}{suffix}").unlink(missing_ok=True)
        (csv_output / f"{legacy_name}.csv").unlink(missing_ok=True)
    for derived_name in ("replicas_by_service", "total_replicas"):
        for suffix in (".png", ".pdf"):
            (plots_output / f"{derived_name}{suffix}").unlink(missing_ok=True)
        (csv_output / f"{derived_name}.csv").unlink(missing_ok=True)

    slo_ms = None
    generated_config = experiment_dir / "config" / "load-gen.yaml"
    if generated_config.exists():
        import yaml

        config = yaml.safe_load(generated_config.read_text(encoding="utf-8")) or {}
        slo_ms = config.get("slo_ms")

    for filename, value_col, output_name, label in COMPARISON_METRICS:
        samples = []
        for run_csv_dir in sorted((experiment_dir / "runs").glob("run-*/load-gen/csv")):
            frame = read_csv(run_csv_dir / filename)
            if frame.empty or not {"t_min", value_col}.issubset(frame.columns):
                continue
            columns = ["t_min", value_col]
            if filename == "p95_response_time.csv" and "window_s" in frame.columns:
                columns.append("window_s")
            samples.append(frame[columns])
        if not samples:
            continue
        merged = pd.concat(samples, ignore_index=True)
        aggregate = merged.groupby("t_min", as_index=False)[value_col].mean()
        if filename == "p95_response_time.csv" and "window_s" in merged.columns:
            window_values = pd.to_numeric(merged["window_s"], errors="coerce").dropna()
            if not window_values.empty:
                aggregate["window_s"] = window_values.iloc[0]
                label = p95_response_time_label(aggregate)
        aggregate.to_csv(csv_output / f"{output_name}.csv", index=False)
        save_line_plot(
            aggregate,
            plots_output / output_name,
            "t_min",
            value_col,
            label,
            hline=float(slo_ms) if filename == "p95_response_time.csv" and slo_ms is not None else None,
            hline_label=f"SLO ({float(slo_ms):g} ms)" if filename == "p95_response_time.csv" and slo_ms is not None else None,
        )

    replica_samples = []
    per_service_samples = []
    for run_csv_dir in sorted((experiment_dir / "runs").glob("run-*/load-gen/csv")):
        frame = read_csv(run_csv_dir / "replicas.csv")
        if not frame.empty and {"t_min", "replicas", "service"}.issubset(frame.columns):
            replica_samples.append(frame[frame["service"] == "__total__"][["t_min", "replicas"]])
            services = frame[~frame["service"].astype(str).str.startswith("__")][
                ["t_min", "service", "replicas"]
            ]
            if not services.empty:
                per_service_samples.append(services)
    if replica_samples:
        replicas = pd.concat(replica_samples, ignore_index=True).groupby("t_min", as_index=False)["replicas"].mean()
        replicas.to_csv(csv_output / "total_replicas.csv", index=False)
        save_line_plot(
            replicas,
            plots_output / "total_replicas",
            "t_min",
            "replicas",
            REPLICA_COUNT_LABEL,
            integer_y=True,
        )
    if per_service_samples:
        per_service = (
            pd.concat(per_service_samples, ignore_index=True)
            .groupby(["t_min", "service"], as_index=False)["replicas"]
            .mean()
        )
        per_service["service_label"] = per_service["service"].map(compact_service_label)
        per_service[["t_min", "service_label", "replicas"]].to_csv(
            csv_output / "replicas_by_service.csv", index=False
        )
        save_line_plot(
            per_service,
            plots_output / "replicas_by_service",
            "t_min",
            "replicas",
            REPLICA_COUNT_LABEL,
            "service_label",
            legend_outside=True,
            legend_ncol=4,
            figsize=(3.5, 2.625),
            integer_y=True,
            x_right_padding_fraction=0.03,
        )


def compare_experiments(experiments: list[tuple[str, Path]], output_dir: Path) -> None:
    if len(experiments) < 2:
        raise ValueError("at least two experiments are required")
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.png", "*.pdf"):
        for path in plots_dir.glob(pattern):
            path.unlink()
    for path in output_dir.glob("*.csv"):
        path.unlink()
    comparison: dict[str, object] = {"experiments": [], "metrics": {}}

    for filename, value_col, output_name, label in COMPARISON_METRICS:
        frames = []
        for experiment_label, experiment_dir in experiments:
            runs = sorted((experiment_dir / "runs").glob("run-*/load-gen/csv"))
            samples = []
            for csv_dir in runs:
                frame = read_csv(csv_dir / filename)
                if not frame.empty and {"t_min", value_col}.issubset(frame.columns):
                    samples.append(frame[["t_min", value_col]])
            if samples:
                merged = pd.concat(samples, ignore_index=True)
                averaged = merged.groupby("t_min", as_index=False)[value_col].mean()
                averaged["experiment"] = experiment_label
                frames.append(averaged)
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined.to_csv(output_dir / f"{output_name}.csv", index=False)
            save_line_plot(combined, plots_dir / output_name, "t_min", value_col, label, "experiment")

    replica_frames = []
    for experiment_label, experiment_dir in experiments:
        samples = []
        for csv_dir in sorted((experiment_dir / "runs").glob("run-*/load-gen/csv")):
            frame = read_csv(csv_dir / "replicas.csv")
            if not frame.empty and {"t_min", "replicas", "service"}.issubset(frame.columns):
                samples.append(frame[frame["service"] == "__total__"][["t_min", "replicas"]])
        if samples:
            averaged = pd.concat(samples, ignore_index=True).groupby("t_min", as_index=False)["replicas"].mean()
            averaged["experiment"] = experiment_label
            replica_frames.append(averaged)
    if replica_frames:
        replicas = pd.concat(replica_frames, ignore_index=True)
        replicas.to_csv(output_dir / "total_replicas.csv", index=False)
        save_line_plot(
            replicas,
            plots_dir / "total_replicas",
            "t_min",
            "replicas",
            REPLICA_COUNT_LABEL,
            "experiment",
            integer_y=True,
        )

    summaries = []
    for experiment_label, experiment_dir in experiments:
        summary_path = experiment_dir / "summary.json"
        if not summary_path.exists():
            continue
        document = json.loads(summary_path.read_text(encoding="utf-8"))
        metrics = document.get("metrics", {})
        summaries.append({"experiment": experiment_label, "metrics": metrics})
        comparison["experiments"].append({
            "name": experiment_label,
            "path": str(experiment_dir),
            "successfulRuns": document.get("successfulRuns", 0),
            "metrics": metrics,
        })
    summary_comparisons = [
        ("failure_percentage", "failure_percentage", "Failure percentage (%)"),
        ("response_time_ms.p95_overall", "overall_p95", "P95 response time (ms)"),
        ("throughput.mean", "mean_throughput", REQUEST_THROUGHPUT_LABEL),
        (
            "scheduling_duration_s.mean",
            "scheduling_mean",
            "Mean pod creation-to-scheduled time (s)",
        ),
        ("total_replicas.mean", "mean_replicas", REPLICA_COUNT_LABEL),
    ]
    for metric_name, output_name, label in summary_comparisons:
        rows = [
            {"experiment": item["experiment"], "value": item["metrics"][metric_name]}
            for item in summaries if isinstance(item["metrics"].get(metric_name), (int, float))
        ]
        if not rows:
            continue
        comparison["metrics"][metric_name] = {row["experiment"]: row["value"] for row in rows}
        frame = pd.DataFrame(rows)
        frame.to_csv(output_dir / f"{output_name}.csv", index=False)
        save_comparison_bar(frame, plots_dir / output_name, label)
    (output_dir / "summary.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")


def save_comparison_bar(df: pd.DataFrame, output_base: Path, y_label: str) -> None:
    apply_style()
    fig, ax = plt.subplots()
    colors = [PAPER_COLORS[index % len(PAPER_COLORS)] for index in range(len(df))]
    ax.bar(df["experiment"], df["value"], color=colors)
    ax.set_ylabel(y_label)
    ax.tick_params(axis="x", rotation=25)
    set_nice_axis_scale(ax, "y", float(pd.to_numeric(df["value"]).max()))
    fig.tight_layout(pad=0.5)
    for suffix in [".pdf", ".png"]:
        fig.savefig(output_base.with_suffix(suffix))
    plt.close(fig)
