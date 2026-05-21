from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    date: date | None
    value: float | None
    unit: str
    change_1: float | None = None
    change_5: float | None = None
    change_week: float | None = None


def from_fred_millions(
    key: str,
    label: str,
    observations: list,
    unit: str = "100m_usd",
) -> Metric:
    if not observations:
        return Metric(key, label, None, None, unit)
    latest = observations[-1]
    value = latest.value / 100.0
    return Metric(
        key=key,
        label=label,
        date=latest.date,
        value=value,
        unit=unit,
        change_1=_change_100m(observations, 1),
        change_5=_change_100m(observations, 5),
        change_week=_change_100m(observations, 1),
    )


def from_fred_rate(key: str, label: str, observations: list) -> Metric:
    if not observations:
        return Metric(key, label, None, None, "percent")
    latest = observations[-1]
    previous = observations[-2] if len(observations) >= 2 else None
    change_bp = None if previous is None else (latest.value - previous.value) * 100
    return Metric(key, label, latest.date, latest.value, "percent", change_1=change_bp)


def net_liquidity(walcl: Metric, tga: Metric, rrp: Metric) -> Metric:
    if walcl.value is None or tga.value is None or rrp.value is None:
        return Metric("net_liquidity", "净流动性", None, None, "100m_usd")
    change_week = None
    if walcl.change_week is not None and tga.change_week is not None and rrp.change_week is not None:
        change_week = walcl.change_week - tga.change_week - rrp.change_week
    return Metric(
        key="net_liquidity",
        label="净流动性",
        date=max(filter(None, [walcl.date, tga.date, rrp.date])),
        value=walcl.value - tga.value - rrp.value,
        unit="100m_usd",
        change_week=change_week,
    )


def spread_bp(left: Metric, right: Metric, key: str, label: str) -> Metric:
    if left.value is None or right.value is None:
        return Metric(key, label, None, None, "bp")
    return Metric(
        key=key,
        label=label,
        date=max(filter(None, [left.date, right.date])),
        value=(left.value - right.value) * 100,
        unit="bp",
    )


def _change_100m(observations: list, offset: int) -> float | None:
    if len(observations) <= offset:
        return None
    return (observations[-1].value - observations[-1 - offset].value) / 100.0
