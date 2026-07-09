import tempfile
import unittest
from pathlib import Path

import pandas as pd

from loadgen.kube import ReplicaSampler, scheduling_duration_seconds
from loadgen.runner import scheduling_summary


class KubernetesSchedulingStatsTest(unittest.TestCase):
    def test_records_pod_scheduling_duration(self) -> None:
        sampler = ReplicaSampler(namespace="default", output_csv=Path("replicas.csv"))
        sampler._start_ts = 100.0

        sampler._record_pods(
            {
                "items": [
                    {
                        "metadata": {
                            "name": "frontend-abc",
                            "uid": "pod-1",
                            "creationTimestamp": "2026-07-09T08:00:00Z",
                            "labels": {"app": "frontend", "group": "onlineboutique"},
                        },
                        "spec": {
                            "schedulerName": "scheduler-plugins-scheduler",
                            "nodeName": "worker-1",
                        },
                        "status": {
                            "phase": "Running",
                            "conditions": [
                                {
                                    "type": "PodScheduled",
                                    "status": "True",
                                    "lastTransitionTime": "2026-07-09T08:00:01.250Z",
                                }
                            ],
                        },
                    }
                ]
            },
            now=105.0,
        )

        row = sampler._pod_rows["pod-1"]
        self.assertEqual(row["pod"], "frontend-abc")
        self.assertEqual(row["service"], "frontend")
        self.assertEqual(row["scheduler"], "scheduler-plugins-scheduler")
        self.assertEqual(row["scheduled"], True)
        self.assertEqual(row["scheduling_duration_s"], 1.25)

    def test_scheduling_summary_groups_by_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_dir = root / "csv"
            csv_dir.mkdir()
            pd.DataFrame(
                [
                    {"pod": "a", "scheduler": "default-scheduler", "scheduling_duration_s": 0.5},
                    {"pod": "b", "scheduler": "scheduler-plugins-scheduler", "scheduling_duration_s": 1.5},
                    {"pod": "c", "scheduler": "scheduler-plugins-scheduler", "scheduling_duration_s": 2.5},
                    {"pod": "pending", "scheduler": "default-scheduler", "scheduling_duration_s": ""},
                ]
            ).to_csv(csv_dir / "scheduling.csv", index=False)

            summary = scheduling_summary(root)

            assert summary is not None
            self.assertEqual(summary["pods"], 3)
            self.assertEqual(summary["max"], 2.5)
            self.assertEqual(summary["by_scheduler"]["default-scheduler"]["pods"], 1)
            self.assertEqual(summary["by_scheduler"]["scheduler-plugins-scheduler"]["pods"], 2)

    def test_scheduling_duration_ignores_missing_timestamps(self) -> None:
        self.assertIsNone(scheduling_duration_seconds("", "2026-07-09T08:00:01Z"))


if __name__ == "__main__":
    unittest.main()
