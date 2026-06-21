from __future__ import annotations

import math
import os
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
SUCCESSFUL_THROUGHPUT_LABEL = "Successful requests (req/s)"
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
    if "window_s" in df.columns:
        window_values = pd.to_numeric(df["window_s"], errors="coerce").dropna()
        if not window_values.empty:
            w = int(window_values.iloc[0])
            return f"P95 response time — {w}s window mean (ms)"
    return "P95 response time (ms)"


def plot_run(run_dir: Path, slo_ms: float | None = None, output_dir: Path | None = None) -> Path:
    csv_dir = run_dir / "csv"
    plot_dir = output_dir or (run_dir / "plots")

    planned = read_run_csv(csv_dir, run_dir, "ideal_rps.csv")
    save_ideal_rps_plot(planned, plot_dir / "ideal_rps")

    actual = read_run_csv(csv_dir, run_dir, "actual_rps.csv")
    save_line_plot(actual, plot_dir / "actual_rps", "t_min", "actual_rps", REQUEST_THROUGHPUT_LABEL)

    failures = read_run_csv(csv_dir, run_dir, "failed_rps.csv")
    save_line_plot(failures, plot_dir / "failed_rps", "t_min", "failed_rps", FAILED_THROUGHPUT_LABEL)

    successful = read_run_csv(csv_dir, run_dir, "successful_rps.csv")
    save_line_plot(
        successful,
        plot_dir / "successful_rps",
        "t_min",
        "successful_rps",
        SUCCESSFUL_THROUGHPUT_LABEL,
    )

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
