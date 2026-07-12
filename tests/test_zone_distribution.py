import unittest

from loadgen.runner import (
    normalize_endpoints,
    validate_zone_distribution,
    zone_distribution_duration,
)


class ZoneDistributionTest(unittest.TestCase):
    def test_validates_mixed_timeline_and_preserves_endpoint_zones(self) -> None:
        endpoints = normalize_endpoints(
            [
                {"url": "http://a1", "zone": "zone-a"},
                {"url": "http://a2", "zone": "zone-a"},
                {"url": "http://b1", "zone": "zone-b"},
            ],
            "endpoints",
        )
        distribution = {
            "type": "mixed",
            "parts": [
                {"type": "constant_weights", "duration": "5m", "weights": {"zone-a": 1, "zone-b": 0}},
                {
                    "type": "linear_weights",
                    "duration": "10m",
                    "start_weights": {"zone-a": 1, "zone-b": 0},
                    "end_weights": {"zone-a": 0, "zone-b": 1},
                },
            ],
        }
        validate_zone_distribution(distribution, {endpoint["zone"] for endpoint in endpoints})
        self.assertEqual(zone_distribution_duration(distribution), 900)
        self.assertEqual([endpoint["zone"] for endpoint in endpoints], ["zone-a", "zone-a", "zone-b"])

    def test_rejects_legacy_spread_distribution(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported zone_distribution type"):
            validate_zone_distribution(
                {"type": "constant", "duration": "1m", "primary_zone": "zone-c", "spread": 0.5},
                {"zone-a", "zone-b"},
            )

    def test_accepts_weighted_transitions(self) -> None:
        distribution = {
            "type": "mixed",
            "parts": [
                {"type": "constant_weights", "duration": "5m", "weights": {"zone-a": 1, "zone-b": 0}},
                {
                    "type": "linear_weights",
                    "duration": "10m",
                    "start_weights": {"zone-a": 1, "zone-b": 0},
                    "end_weights": {"zone-a": 0, "zone-b": 1},
                },
            ],
        }
        validate_zone_distribution(distribution, {"zone-a", "zone-b", "zone-c"})
        self.assertEqual(zone_distribution_duration(distribution), 900)

    def test_rejects_invalid_weight_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown zones"):
            validate_zone_distribution(
                {"type": "constant_weights", "duration": "1m", "weights": {"zone-z": 1}},
                {"zone-a", "zone-b"},
            )
        with self.assertRaisesRegex(ValueError, "positive total weight"):
            validate_zone_distribution(
                {"type": "constant_weights", "duration": "1m", "weights": {"zone-a": 0}},
                {"zone-a", "zone-b"},
            )


if __name__ == "__main__":
    unittest.main()
