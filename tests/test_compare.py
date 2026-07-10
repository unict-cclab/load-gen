import json

import pandas as pd

from loadgen.plots import compare_experiments


def test_compare_experiments_averages_runs_and_writes_summary(tmp_path):
    experiments = []
    for label, values in [("baseline", ([10, 20], [20, 40])), ("candidate", ([30, 50], [50, 70]))]:
        root = tmp_path / label
        for index, run_values in enumerate(values, start=1):
            csv_dir = root / "runs" / f"run-{index:03d}" / "load-gen" / "csv"
            csv_dir.mkdir(parents=True)
            pd.DataFrame({"t_min": [0, 1], "actual_rps": run_values}).to_csv(csv_dir / "actual_rps.csv", index=False)
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

    frame = pd.read_csv(output / "actual_rps.csv")
    baseline = frame[frame["experiment"] == "baseline"]
    assert baseline["actual_rps"].tolist() == [15.0, 30.0]
    summary = json.loads((output / "summary.json").read_text())
    assert len(summary["experiments"]) == 2
    assert (output / "plots" / "actual_rps.png").exists()
    assert (output / "plots" / "summary_throughput_mean.png").exists()
    assert (output / "overall_p95.csv").exists()
    assert (output / "plots" / "overall_p95.png").exists()
