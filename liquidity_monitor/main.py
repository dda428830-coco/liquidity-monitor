from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from liquidity_monitor.analyzers.liquidity_calc import (
    Metric,
    from_fred_billions,
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
    metrics, data_warnings = collect_metrics(cfg)
    assessment = assess(metrics, cfg, data_warnings=data_warnings)
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


def collect_metrics(cfg: dict) -> tuple[dict[str, Metric], list[str]]:
    fred = FredFetcher()
    series_cfg = cfg["series"]
    raw: dict[str, list[Observation]] = {}
    data_warnings: list[str] = []
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

    raw["rrp"] = _sanitize_rrp_observations(raw["rrp"], data_warnings)
    tga = _treasury_tga_metric(raw.get("tga_fred", []), data_warnings)
    metrics = {
        "walcl": from_fred_millions("walcl", "美联储总资产", raw["walcl"]),
        "tga": tga,
        "rrp": from_fred_billions("rrp", "逆回购余额", raw["rrp"]),
        "reserves": from_fred_millions("reserves", "银行准备金", raw["reserves"]),
        "sofr": from_fred_rate("sofr", "SOFR", raw["sofr"]),
        "iorb": from_fred_rate("iorb", "IORB", raw["iorb"]),
        "dgs10": from_fred_rate("dgs10", "10年美债收益率", raw["dgs10"]),
        "dgs2": from_fred_rate("dgs2", "2年美债收益率", raw["dgs2"]),
        "curve_10y2y": from_fred_rate("curve_10y2y", "10-2利差", raw["curve_10y2y"]),
    }
    metrics["net_liquidity"] = net_liquidity(metrics["walcl"], metrics["tga"], metrics["rrp"])
    metrics["sofr_iorb"] = spread_bp(metrics["sofr"], metrics["iorb"], "sofr_iorb", "SOFR-IORB")
    _append_cross_checks(metrics, data_warnings)
    return metrics, data_warnings


def _treasury_tga_metric(fred_fallback: list[Observation], data_warnings: list[str]) -> Metric:
    fred_metric = from_fred_millions("tga", "TGA余额", fred_fallback)
    try:
        balances = TreasuryFetcher().latest_tga()
    except Exception as exc:
        data_warnings.append(f"Treasury Daily Statement暂不可用，TGA回退FRED WTREGEN: {exc}")
        return fred_metric

    if not balances:
        data_warnings.append("Treasury Daily Statement没有返回TGA余额，TGA回退FRED WTREGEN。")
        return fred_metric

    latest = balances[-1]
    previous = balances[-2] if len(balances) >= 2 else None
    week_previous = balances[-6] if len(balances) >= 6 else previous
    dts_metric = Metric(
        key="tga",
        label="TGA余额",
        date=latest.date,
        value=latest.value_100m_usd,
        unit="100m_usd",
        change_1=None if previous is None else latest.value_100m_usd - previous.value_100m_usd,
        change_week=None if week_previous is None else latest.value_100m_usd - week_previous.value_100m_usd,
    )
    data_warnings.append(
        f"TGA DTS口径: {latest.account_type or '未知account_type'}，日期{latest.date.isoformat()}，值{latest.value_100m_usd:.0f}亿。"
    )

    if fred_metric.value is None:
        return dts_metric

    diff = abs(dts_metric.value - fred_metric.value)
    if diff > 1000:
        data_warnings.append(
            "TGA DTS与FRED WTREGEN差异超过1000亿，"
            f"本次净流动性采用FRED值{fred_metric.value:.0f}亿；DTS值{dts_metric.value:.0f}亿需核对口径/字段。"
        )
        return fred_metric

    return dts_metric


def _sanitize_rrp_observations(
    observations: list[Observation],
    data_warnings: list[str],
) -> list[Observation]:
    if not observations:
        data_warnings.append("RRP序列为空，已跳过RRP阈值判断。")
        return observations
    latest = observations[-1]
    if latest.value != 0:
        return observations

    recent_positive = [item for item in observations[-10:] if item.value > 0]
    if recent_positive:
        replacement = recent_positive[-1]
        data_warnings.append(
            "RRP最新值为0，疑似非交易日/占位/延迟数据；"
            f"本次改用{replacement.date.isoformat()}的非零值{replacement.value * 10:.0f}亿。"
        )
        return [item for item in observations if item.date <= replacement.date]

    data_warnings.append("RRP最近10条数据均为0，已保留原值；请核对纽约联储ON RRP原始数据。")
    return observations


def _append_cross_checks(
    metrics: dict[str, Metric],
    data_warnings: list[str],
) -> None:
    tga = metrics.get("tga")
    if tga and tga.value is not None and tga.value < 3000:
        data_warnings.append(
            f"TGA为{tga.value:.0f}亿，处于极低水位；请核对Treasury DTS是否取到总Federal Reserve Account。"
        )

    spread = metrics.get("sofr_iorb")
    if spread and spread.value is not None and spread.value < -5:
        data_warnings.append(
            f"SOFR-IORB为{spread.value:.0f}bp，低于常规监控区间；请核对SOFR和IORB日期是否一致。"
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
