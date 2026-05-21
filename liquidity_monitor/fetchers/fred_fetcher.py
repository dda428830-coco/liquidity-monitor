from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import Iterable

from liquidity_monitor.common.http import get_json, get_text


FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@dataclass(frozen=True)
class Observation:
    series_id: str
    date: date
    value: float


class FredFetcher:
    def __init__(self, api_key: str | None = None, timeout: int = 10) -> None:
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self.timeout = timeout

    def latest(self, series_id: str, limit: int = 120) -> list[Observation]:
        if self.api_key:
            return self._latest_from_api(series_id, limit)
        return self._latest_from_public_csv(series_id, limit)

    def _latest_from_api(self, series_id: str, limit: int) -> list[Observation]:
        payload = get_json(
            FRED_API_URL,
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": str(limit),
            },
            timeout=self.timeout,
        )
        rows = payload.get("observations", [])
        observations = [
            Observation(series_id, _parse_date(row["date"]), float(row["value"]))
            for row in rows
            if row.get("value") not in (None, ".")
        ]
        return sorted(observations, key=lambda item: item.date)

    def _latest_from_public_csv(self, series_id: str, limit: int) -> list[Observation]:
        text = get_text(FRED_CSV_URL, params={"id": series_id}, timeout=self.timeout)
        rows = list(csv.DictReader(StringIO(text)))
        observations = []
        for row in rows[-limit * 2 :]:
            value = row.get(series_id)
            if value in (None, "."):
                continue
            observations.append(
                Observation(series_id, _parse_date(row["observation_date"]), float(value))
            )
        return observations[-limit:]


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def latest_value(observations: Iterable[Observation]) -> Observation | None:
    items = sorted(observations, key=lambda item: item.date)
    return items[-1] if items else None


def previous_value(observations: Iterable[Observation], offset: int = 1) -> Observation | None:
    items = sorted(observations, key=lambda item: item.date)
    if len(items) <= offset:
        return None
    return items[-1 - offset]
