import json

import pandas as pd

from loadgen.plots import aggregate_experiment, compare_experiments, summary_metric_label


def test_summary_metric_labels_match_original_plot_labels():
    assert summary_metric_label("throughput.mean") == "Throughput (req/s)"
    assert summary_metric_label("failed_rps.mean") == "Failed requests (req/s)"
    assert summary_metric_label("replicas.mean") == "Replica count"
    assert summary_metric_label("response_time_ms.p95_overall") == "P95 response time (ms)"


def test_aggregate_experiment_uses_canonical_single_experiment_plots(tmp_path):
    root = tmp_path / "experiment"
    for index, values in enumerate(([10, 20], [20, 40]), start=1):
        csv_dir = root / "runs" / f"run-{index:03d}" / "load-gen" / "csv"
        csv_dir.mkdir(parents=True)
        pd.DataFrame({"t_min": [0, 1], "throughput_rps": values}).to_csv(
            csv_dir / "throughput_rps.csv", index=False
        )
        pd.DataFrame({"t_min": [0, 1], "p95_ms": [100, 200], "window_s": [30, 30]}).to_csv(
            csv_dir / "p95_response_time.csv", index=False
        )

    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "load-gen.yaml").write_text("slo_ms: 250\n", encoding="utf-8")

    aggregate_experiment(root)

    throughput = pd.read_csv(root / "csv" / "throughput_rps.csv")
    assert throughput["throughput_rps"].tolist() == [15.0, 30.0]
    assert (root / "plots" / "throughput_rps.png").exists()
    assert (root / "plots" / "p95_response_time.png").exists()


def test_compare_experiments_averages_runs_and_writes_summary(tmp_path):
    experiments = []
    for label, values in [("baseline", ([10, 20], [20, 40])), ("candidate", ([30, 50], [50, 70]))]:
        root = tmp_path / label
        for index, run_values in enumerate(values, start=1):
            csv_dir = root / "runs" / f"run-{index:03d}" / "load-gen" / "csv"
            csv_dir.mkdir(parents=True)
            pd.DataFrame({"t_min": [0, 1], "throughput_rps": run_values}).to_csv(
                csv_dir / "throughput_rps.csv", index=False
            )
        (root / "summary.json").write_text(json.dumps({
            "successfulRuns": 2,
            "metrics": {
                "throughput.mean": sum(values[0]) / 2,
                "response_time_ms.p95_overall": 200 if label == "baseline" else 150,
            },
        }))
        experiments.append((label, root))

    output = tmp_path / "comparison"
    compare_experiments(experiments, output)

    frame = pd.read_csv(output / "throughput_rps.csv")
    baseline = frame[frame["experiment"] == "baseline"]
    assert baseline["throughput_rps"].tolist() == [15.0, 30.0]
    summary = json.loads((output / "summary.json").read_text())
    assert len(summary["experiments"]) == 2
    assert (output / "plots" / "throughput_rps.png").exists()
    assert (output / "plots" / "summary_throughput_mean.png").exists()
    assert (output / "overall_p95.csv").exists()
    assert (output / "plots" / "overall_p95.png").exists()
