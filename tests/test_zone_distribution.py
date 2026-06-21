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
                {"type": "constant", "duration": "5m", "primary_zone": "zone-a", "spread": 0},
                {"type": "linear", "duration": "10m", "primary_zone": "zone-a", "start_spread": 0, "end_spread": 1},
            ],
        }
        validate_zone_distribution(distribution, {endpoint["zone"] for endpoint in endpoints})
        self.assertEqual(zone_distribution_duration(distribution), 900)
        self.assertEqual([endpoint["zone"] for endpoint in endpoints], ["zone-a", "zone-a", "zone-b"])

    def test_rejects_unknown_primary_zone(self) -> None:
        with self.assertRaisesRegex(ValueError, "is not present"):
            validate_zone_distribution(
                {"type": "constant", "duration": "1m", "primary_zone": "zone-c", "spread": 0.5},
                {"zone-a", "zone-b"},
            )


if __name__ == "__main__":
    unittest.main()
