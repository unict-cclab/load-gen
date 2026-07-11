import tempfile
import unittest
from pathlib import Path

import pandas as pd

from loadgen.plots import p95_response_time_label
from loadgen.runner import failure_percentage_summary, normalize_locust_history


class ResponseTimeMetricsTest(unittest.TestCase):
    def test_normalizes_p95_as_window_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locust_dir = root / "locust"
            csv_dir = root / "csv"
            locust_dir.mkdir()
            csv_dir.mkdir()

            pd.DataFrame(
                [
                    history_row(100, 12.0, 0.0, "N/A"),
                    history_row(101, 12.0, 0.5, 120),
                    history_row(102, 13.0, 0.0, 200),
                    history_row(103, 14.0, 1.0, 150),
                    history_row(104, 15.0, 0.0, 180),
                ]
            ).to_csv(locust_dir / "locust_stats_history.csv", index=False)

            normalize_locust_history(locust_dir, csv_dir, p95_window_s=2.0)

            p95 = pd.read_csv(csv_dir / "p95_response_time.csv")
            self.assertEqual(p95["p95_ms"].tolist(), [200, 180])
            self.assertEqual(p95["window_s"].tolist(), [2.0, 2.0])

            throughput = pd.read_csv(csv_dir / "throughput_rps.csv")
            self.assertEqual(throughput["throughput_rps"].tolist(), [12.0, 11.5, 13.0, 13.0, 15.0])
            self.assertFalse((csv_dir / "actual_rps.csv").exists())
            self.assertFalse((csv_dir / "successful_rps.csv").exists())

    def test_p95_label_matches_window_max_aggregation(self) -> None:
        label = p95_response_time_label(pd.DataFrame({"window_s": [5.0]}))
        self.assertEqual(label, "P95 response time (ms)")

    def test_failure_percentage_uses_successful_and_failed_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_dir = root / "csv"
            csv_dir.mkdir()
            pd.DataFrame({"throughput_rps": [90, 80]}).to_csv(csv_dir / "throughput_rps.csv", index=False)
            pd.DataFrame({"failed_rps": [10, 20]}).to_csv(csv_dir / "failed_rps.csv", index=False)
            self.assertEqual(failure_percentage_summary(root), 15.0)


def history_row(
    timestamp: int,
    requests_per_second: float,
    failures_per_second: float,
    p95: object,
) -> dict[str, object]:
    return {
        "Timestamp": timestamp,
        "User Count": 1,
        "Type": "",
        "Name": "Aggregated",
        "Requests/s": requests_per_second,
        "Failures/s": failures_per_second,
        "95%": p95,
        "Total Request Count": 1,
        "Total Failure Count": 0,
        "Total Median Response Time": 0,
        "Total Average Response Time": 0,
        "Total Min Response Time": 0,
        "Total Max Response Time": 0,
        "Total Average Content Size": 0,
    }


if __name__ == "__main__":
    unittest.main()
