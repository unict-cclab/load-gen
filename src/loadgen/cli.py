from __future__ import annotations

import argparse
from pathlib import Path

from .patterns import sample_pattern
from .plots import plot_run, save_line_plot
from .runner import artifact_dirs, experiment_dir, load_config, normalize_locust_history, run_experiment, write_summary


def main() -> None:
    parser = argparse.ArgumentParser(prog="load-gen", description="Locust experiment helper")
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview", help="Generate ideal workload CSV/plots without running Locust")
    preview.add_argument("-c", "--config", required=True, type=Path)

    run = sub.add_parser("run", help="Run one Locust experiment")
    run.add_argument("-c", "--config", required=True, type=Path)
    run.add_argument("--dry-run", action="store_true", help="Create generated files and ideal workload only")

    plot = sub.add_parser("plot", help="Regenerate plots for an experiment config")
    plot.add_argument("-c", "--config", required=True, type=Path)
    plot.add_argument("--slo-ms", type=float)

    plot_csv = sub.add_parser("plot-csv", help="Regenerate plots from an experiment config")
    plot_csv.add_argument("-c", "--config", required=True, type=Path)
    plot_csv.add_argument("--slo-ms", type=float)
    plot_csv.add_argument("--output-dir", type=Path, help="Override the output plot directory")

    args = parser.parse_args()

    if args.command == "preview":
        cfg = load_config(args.config)
        out = resolve_run_dir(args.config, cfg)
        dirs = artifact_dirs(out)
        preview_csv = dirs.preview / "csv"
        preview_plots = dirs.preview / "plots"
        preview_csv.mkdir(parents=True, exist_ok=True)
        preview_plots.mkdir(parents=True, exist_ok=True)
        ideal = sample_pattern(cfg["pattern"], step_s=float(cfg.get("sample_interval_s", 1.0)))
        ideal.to_csv(preview_csv / "ideal_rps.csv", index=False)
        save_line_plot(ideal, preview_plots / "ideal_rps", "t_min", "ideal_rps", "Ideal RPS")
        print(f"preview written to {dirs.preview}")
        return

    if args.command == "run":
        run_dir = run_experiment(args.config, dry_run=args.dry_run)
        print(f"run written to {run_dir}")
        return

    if args.command == "plot":
        cfg = load_config(args.config)
        run_dir = resolve_run_dir(args.config, cfg)
        plot_dir = plot_run(run_dir, slo_ms=args.slo_ms if args.slo_ms is not None else cfg.get("slo_ms"))
        print(f"plots written to {plot_dir}")
        return

    if args.command == "plot-csv":
        cfg = load_config(args.config)
        run_dir = resolve_run_dir(args.config, cfg)
        p95_window_s = cfg.get("p95_window_s")
        dirs = artifact_dirs(run_dir)
        locust_dir = dirs.locust if dirs.locust.exists() else run_dir
        csv_dir = dirs.csv
        csv_dir.mkdir(parents=True, exist_ok=True)
        if p95_window_s is not None:
            normalize_locust_history(locust_dir, csv_dir, p95_window_s=float(p95_window_s))
            write_summary(run_dir, dry_run=False, locust_exit=None)
        plot_dir = plot_run(
            run_dir,
            slo_ms=args.slo_ms if args.slo_ms is not None else cfg.get("slo_ms"),
            output_dir=args.output_dir,
        )
        print(f"plots written to {plot_dir}")
        return


def resolve_run_dir(path: Path, cfg: dict | None = None) -> Path:
    if path.is_file() and path.suffix.lower() in {".yaml", ".yml", ".json"}:
        cfg = cfg or load_config(path)
        return experiment_dir(path, cfg).resolve()

    raise SystemExit(
        f"expected a YAML/JSON config file, got: {path}"
    )


if __name__ == "__main__":
    main()
