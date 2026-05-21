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
    account_type: str
    source: str = "Treasury Daily Statement"


class TreasuryFetcher:
    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def latest_tga(self, limit: int = 30) -> list[TreasuryBalance]:
        payload = get_json(
            TREASURY_OCB_URL,
            params={
                "fields": "record_date,account_type,close_today_bal,open_today_bal,open_month_bal",
                "sort": "-record_date",
                "page[size]": str(limit),
            },
            timeout=self.timeout,
        )
        data = payload.get("data", [])
        data = _select_tga_rows(data)
        balances = []
        for row in data:
            raw_value = _pick_balance(row)
            if raw_value is None:
                continue
            balances.append(
                TreasuryBalance(
                    date=datetime.strptime(row["record_date"], "%Y-%m-%d").date(),
                    value_100m_usd=_to_100m_usd(raw_value),
                    account_type=row.get("account_type", ""),
                )
            )
        return sorted(balances, key=lambda item: item.date)


def _select_tga_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    by_date: dict[str, list[dict]] = {}
    for row in rows:
        by_date.setdefault(row.get("record_date", ""), []).append(row)

    selected = []
    for record_date, date_rows in by_date.items():
        if not record_date:
            continue
        row = _pick_tga_row(date_rows)
        if row is not None:
            selected.append(row)
    return selected


def _pick_tga_row(rows: list[dict]) -> dict | None:
    preferred = (
        "Treasury General Account (TGA) Closing Balance",
        "Federal Reserve Account",
        "Total Operating Balance",
    )
    for account_type in preferred:
        for row in rows:
            if row.get("account_type") == account_type:
                return row
    for row in rows:
        account_type = str(row.get("account_type", "")).lower()
        if "treasury general account" in account_type and "closing" in account_type:
            return row
    return None


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
