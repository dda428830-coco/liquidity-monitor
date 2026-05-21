from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from liquidity_monitor.common.http import get_json


TREASURY_OCB_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    "v1/accounting/dts/operating_cash_balance"
)


@dataclass(frozen=True)
class TreasuryBalance:
    date: date
    value_100m_usd: float
    source: str = "Treasury Daily Statement"


class TreasuryFetcher:
    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def latest_tga(self, limit: int = 10) -> list[TreasuryBalance]:
        payload = get_json(
            TREASURY_OCB_URL,
            params={
                "filter": "account_type:eq:Federal Reserve Account",
                "sort": "-record_date",
                "page[size]": str(limit),
            },
            timeout=self.timeout,
        )
        data = payload.get("data", [])
        balances = []
        for row in data:
            raw_value = _pick_balance(row)
            if raw_value is None:
                continue
            balances.append(
                TreasuryBalance(
                    date=datetime.strptime(row["record_date"], "%Y-%m-%d").date(),
                    value_100m_usd=_to_100m_usd(raw_value),
                )
            )
        return sorted(balances, key=lambda item: item.date)


def _pick_balance(row: dict) -> Decimal | None:
    preferred = (
        "close_today_bal",
        "closing_balance",
        "account_balance",
        "open_today_bal",
    )
    for key in preferred:
        value = row.get(key)
        if value not in (None, ""):
            return _decimal_or_none(value)
    for key, value in row.items():
        if "bal" in key.lower() and value not in (None, ""):
            parsed = _decimal_or_none(value)
            if parsed is not None:
                return parsed
    return None


def _decimal_or_none(value: object) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _to_100m_usd(value: Decimal) -> float:
    abs_value = abs(value)
    if abs_value > Decimal("100000000"):
        return float(value / Decimal("100000000"))
    return float(value / Decimal("100"))
