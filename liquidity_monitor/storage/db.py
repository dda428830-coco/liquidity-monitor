from __future__ import annotations

import sqlite3
from pathlib import Path

from liquidity_monitor.analyzers.liquidity_calc import Metric


SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_history (
    key TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    change_1 REAL,
    change_5 REAL,
    change_week REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (key, date)
);
"""


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save_metrics(self, metrics: dict[str, Metric]) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(SCHEMA)
            for metric in metrics.values():
                if metric.date is None:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO metric_history
                    (key, date, value, unit, change_1, change_5, change_week)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metric.key,
                        metric.date.isoformat(),
                        metric.value,
                        metric.unit,
                        metric.change_1,
                        metric.change_5,
                        metric.change_week,
                    ),
                )
