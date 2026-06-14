from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd


_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)([hms])")


@dataclass(frozen=True)
class PatternPoint:
    t_s: float
    rps: float


def parse_duration(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("duration must be non-negative")
        return float(value)

    text = str(value).strip()
    if not text:
        raise ValueError("duration must not be empty")

    matches = list(_DURATION_RE.finditer(text))
    if not matches:
        raise ValueError(f"unsupported duration: {value!r}")

    consumed = "".join(match.group(0) for match in matches)
    if consumed != text:
        raise ValueError(f"unsupported duration: {value!r}")

    unit_s = {"h": 3600.0, "m": 60.0, "s": 1.0}
    return sum(float(match.group(1)) * unit_s[match.group(2)] for match in matches)


def format_duration(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    return f"{int(math.ceil(seconds))}s"


def pattern_duration(pattern: dict[str, Any]) -> float:
    kind = pattern.get("type")
    if kind == "constant":
        return parse_duration(pattern["duration"])
    if kind == "sinusoidal":
        return parse_duration(pattern["duration"])
    if kind == "exponential":
        return parse_duration(pattern["duration"])
    if kind == "mixed":
        return sum(pattern_duration(part) for part in pattern.get("parts", []))
    raise ValueError(f"unsupported pattern type: {kind!r}")


def rps_at(pattern: dict[str, Any], t_s: float) -> float:
    kind = pattern.get("type")
    if kind == "constant":
        return max(0.0, float(pattern["rps"]))

    if kind == "sinusoidal":
        baseline = float(pattern["baseline_rps"])
        amplitude = float(pattern["amplitude_rps"])
        period_s = parse_duration(pattern["period"])
        phase_s = parse_duration(pattern.get("phase", 0))
        value = baseline + amplitude * math.sin((2.0 * math.pi * (t_s + phase_s)) / period_s)
        return max(0.0, value)

    if kind == "exponential":
        start = float(pattern["start_rps"])
        end = float(pattern["end_rps"])
        duration_s = max(pattern_duration(pattern), 1.0)
        curve = float(pattern.get("curve", 3.0))
        progress = min(max(t_s / duration_s, 0.0), 1.0)
        if abs(curve) < 1e-9:
            value = start + (end - start) * progress
        else:
            shaped = (math.exp(curve * progress) - 1.0) / (math.exp(curve) - 1.0)
            value = start + (end - start) * shaped
        return max(0.0, value)

    if kind == "mixed":
        cursor = 0.0
        parts = pattern.get("parts", [])
        if not parts:
            return 0.0
        for part in parts:
            part_duration = pattern_duration(part)
            if t_s < cursor + part_duration:
                return rps_at(part, t_s - cursor)
            cursor += part_duration
        return rps_at(parts[-1], pattern_duration(parts[-1]))

    raise ValueError(f"unsupported pattern type: {kind!r}")


def sample_pattern(pattern: dict[str, Any], step_s: float = 1.0) -> pd.DataFrame:
    if step_s <= 0:
        raise ValueError("step_s must be positive")

    duration_s = pattern_duration(pattern)
    rows: list[dict[str, float]] = []
    total_samples = max(1, int(math.ceil(duration_s / step_s)))
    for idx in range(total_samples + 1):
        t_s = min(idx * step_s, duration_s)
        rows.append({"t_s": t_s, "t_min": t_s / 60.0, "ideal_rps": rps_at(pattern, t_s)})
    return pd.DataFrame(rows)


def max_rps(pattern: dict[str, Any], step_s: float = 1.0) -> float:
    df = sample_pattern(pattern, step_s=step_s)
    if df.empty:
        return 0.0
    return float(df["ideal_rps"].max())
