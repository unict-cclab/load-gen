from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/loadgen-matplotlib")

import matplotlib.pyplot as plt
import pandas as pd


PAPER_STYLE = {
    "font.family": "serif",
    "font.size": 4.8,
    "axes.labelsize": 4.8,
    "xtick.labelsize": 4.2,
    "ytick.labelsize": 4.2,
    "legend.fontsize": 4.2,
    "figure.figsize": (3.2, 2.4),
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "axes.grid": True,
    "grid.color": "0.88",
    "grid.linewidth": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.45,
}


def apply_style() -> None:
    plt.rcParams.update(PAPER_STYLE)


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
) -> None:
    if df.empty:
        return

    apply_style()
    fig, ax = plt.subplots(figsize=figsize)

    if series_col:
        for label, group in df.groupby(series_col):
            ax.plot(group[x_col], group[y_col], linewidth=0.8, label=str(label))
        if legend_outside:
            ax.legend(
                frameon=False,
                loc="upper center",
                bbox_to_anchor=(0.5, -0.34),
                ncol=legend_ncol or min(4, df[series_col].nunique()),
                columnspacing=0.9,
                handlelength=1.4,
                handletextpad=0.4,
            )
        else:
            ax.legend(frameon=False)
    else:
        ax.plot(df[x_col], df[y_col], linewidth=0.8)

    if hline is not None:
        ax.axhline(hline, color="0.15", linestyle="--", linewidth=0.65, label=hline_label)
        if hline_label and not series_col:
            ax.legend(frameon=False)

    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel(y_label)
    ax.set_xlim(left=0)
    ax.tick_params(width=0.35, length=2.0, pad=1.5)
    fig.tight_layout(pad=0.25)

    output_base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_base.with_suffix(".png"))
    plt.close(fig)


def plot_run(run_dir: Path, slo_ms: float | None = None, output_dir: Path | None = None) -> Path:
    csv_dir = run_dir / "csv"
    plot_dir = output_dir or (run_dir / "plots")

    planned = read_run_csv(csv_dir, run_dir, "ideal_rps.csv")
    save_line_plot(planned, plot_dir / "ideal_rps", "t_min", "ideal_rps", "Ideal RPS")

    actual = read_run_csv(csv_dir, run_dir, "actual_rps.csv")
    save_line_plot(actual, plot_dir / "actual_rps", "t_min", "actual_rps", "Actual RPS")

    failures = read_run_csv(csv_dir, run_dir, "failure_rate.csv")
    save_line_plot(failures, plot_dir / "failure_rate", "t_min", "failure_rate", "Failures/s")

    p95 = read_run_csv(csv_dir, run_dir, "p95_response_time.csv")
    save_line_plot(
        p95,
        plot_dir / "p95_response_time",
        "t_min",
        "p95_ms",
        "P95 response time (ms)",
        hline=slo_ms,
        hline_label=f"SLO ({slo_ms:g} ms)" if slo_ms is not None else None,
    )

    replicas = read_run_csv(csv_dir, run_dir, "replicas.csv")
    if not replicas.empty:
        per_service = replicas[replicas["service"] != "__total__"].copy()
        total = replicas[replicas["service"] == "__total__"].copy()
        if not per_service.empty:
            per_service["service_label"] = per_service["service"].map(compact_service_label)
        save_line_plot(
            per_service,
            plot_dir / "replicas_by_service",
            "t_min",
            "replicas",
            "Replicas",
            "service_label",
            legend_outside=True,
            legend_ncol=4,
            figsize=(3.2, 2.4),
        )
        save_line_plot(total, plot_dir / "total_replicas", "t_min", "replicas", "Total replicas")

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
