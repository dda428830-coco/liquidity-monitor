from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from liquidity_monitor.analyzers.liquidity_calc import (
    Metric,
    from_fred_millions,
    from_fred_rate,
    net_liquidity,
    spread_bp,
)
from liquidity_monitor.analyzers.threshold_check import assess
from liquidity_monitor.fetchers.fred_fetcher import FredFetcher, Observation
from liquidity_monitor.fetchers.treasury_fetcher import TreasuryFetcher
from liquidity_monitor.notifiers.alert_formatter import format_report
from liquidity_monitor.notifiers.discord_pusher import DiscordPusher
from liquidity_monitor.storage.db import HistoryStore


ROOT = Path(__file__).resolve().parent


def main() -> int:
    _configure_output()
    args = _parse_args()
    _load_env(args.env_file)
    cfg = _load_config(args.config)
    metrics = collect_metrics(cfg)
    assessment = assess(metrics, cfg)
    report = format_report(metrics, assessment, cfg)

    HistoryStore(args.db).save_metrics(metrics)

    if args.preview or not os.getenv("DISCORD_WEBHOOK_URL"):
        print(report)
        if not os.getenv("DISCORD_WEBHOOK_URL") and not args.preview:
            print("\n提示: 未设置 DISCORD_WEBHOOK_URL，本次仅打印预览。")
        return 0

    DiscordPusher().send(report)
    print("Discord push sent.")
    return 0


def _configure_output() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def collect_metrics(cfg: dict) -> dict[str, Metric]:
    fred = FredFetcher()
    series_cfg = cfg["series"]
    raw: dict[str, list[Observation]] = {}
    fred_keys = ("walcl", "tga_fred", "rrp", "reserves", "sofr", "iorb", "dgs10", "dgs2", "curve_10y2y")
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(fred.latest, series_cfg[key]): key
            for key in fred_keys
        }
        for future in as_completed(futures):
            key = futures[future]
            series_id = series_cfg[key]
            try:
                raw[key] = future.result()
            except Exception as exc:
                print(f"数据源暂不可用: {series_id}: {exc}")
                raw[key] = []

    tga = _treasury_tga_metric(raw.get("tga_fred", []))
    metrics = {
        "walcl": from_fred_millions("walcl", "美联储总资产", raw["walcl"]),
        "tga": tga,
        "rrp": from_fred_millions("rrp", "逆回购余额", raw["rrp"]),
        "reserves": from_fred_millions("reserves", "银行准备金", raw["reserves"]),
        "sofr": from_fred_rate("sofr", "SOFR", raw["sofr"]),
        "iorb": from_fred_rate("iorb", "IORB", raw["iorb"]),
        "dgs10": from_fred_rate("dgs10", "10年美债收益率", raw["dgs10"]),
        "dgs2": from_fred_rate("dgs2", "2年美债收益率", raw["dgs2"]),
        "curve_10y2y": from_fred_rate("curve_10y2y", "10-2利差", raw["curve_10y2y"]),
    }
    metrics["net_liquidity"] = net_liquidity(metrics["walcl"], metrics["tga"], metrics["rrp"])
    metrics["sofr_iorb"] = spread_bp(metrics["sofr"], metrics["iorb"], "sofr_iorb", "SOFR-IORB")
    return metrics


def _treasury_tga_metric(fred_fallback: list[Observation]) -> Metric:
    try:
        balances = TreasuryFetcher().latest_tga()
    except Exception as exc:
        print(f"Treasury Daily Statement暂不可用，回退FRED WTREGEN: {exc}")
        return from_fred_millions("tga", "TGA余额", fred_fallback)

    if not balances:
        return from_fred_millions("tga", "TGA余额", fred_fallback)

    latest = balances[-1]
    previous = balances[-2] if len(balances) >= 2 else None
    week_previous = balances[-6] if len(balances) >= 6 else previous
    return Metric(
        key="tga",
        label="TGA余额",
        date=latest.date,
        value=latest.value_100m_usd,
        unit="100m_usd",
        change_1=None if previous is None else latest.value_100m_usd - previous.value_100m_usd,
        change_week=None if week_previous is None else latest.value_100m_usd - week_previous.value_100m_usd,
    )


def _load_config(path: Path) -> dict:
    return _parse_simple_yaml(path.read_text(encoding="utf-8"))


def _parse_simple_yaml(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not raw_value:
            child: dict = {}
            current[key] = child
            stack.append((indent, child))
        else:
            current[key] = _parse_scalar(raw_value)
    return root


def _parse_scalar(value: str) -> object:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_env(path: Path | None) -> None:
    if not path or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="USD liquidity monitor with Discord alerts.")
    parser.add_argument("--preview", action="store_true", help="Only print report, do not push Discord.")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "thresholds.yaml")
    parser.add_argument("--env-file", type=Path, default=ROOT / "config" / "secrets.env")
    parser.add_argument("--db", type=Path, default=ROOT / "storage" / "history.db")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
