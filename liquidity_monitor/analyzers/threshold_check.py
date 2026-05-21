from __future__ import annotations

from dataclasses import dataclass

from .liquidity_calc import Metric


SEVERITY_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


@dataclass(frozen=True)
class Alert:
    level: str
    title: str
    detail: str


@dataclass(frozen=True)
class Assessment:
    level: str
    alerts: list[Alert]
    strategy: str


def assess(metrics: dict[str, Metric], cfg: dict) -> Assessment:
    t = cfg["thresholds_100m_usd"]
    bp = cfg["thresholds_bp"]
    alerts: list[Alert] = []

    _check_walcl(metrics.get("walcl"), t, alerts)
    _check_tga(metrics.get("tga"), t, alerts)
    _check_rrp(metrics.get("rrp"), t, alerts)
    _check_reserves(metrics.get("reserves"), t, alerts)
    _check_net(metrics.get("net_liquidity"), t, alerts)
    _check_sofr(metrics.get("sofr"), metrics.get("sofr_iorb"), bp, alerts)
    _check_dgs10(metrics.get("dgs10"), bp, alerts)

    level = _base_level(metrics, cfg)
    for alert in alerts:
        if SEVERITY_ORDER[alert.level] > SEVERITY_ORDER[level]:
            level = alert.level

    return Assessment(level=level, alerts=alerts, strategy=_strategy(level))


def _check_walcl(metric: Metric | None, t: dict, alerts: list[Alert]) -> None:
    if not metric or metric.change_week is None:
        return
    if metric.change_week > t["walcl_week_change_qe"]:
        alerts.append(Alert("green", "美联储资产扩表", f"WALCL周环比增加{metric.change_week:.0f}亿。"))
    elif metric.change_week < t["walcl_week_change_qt"]:
        alerts.append(Alert("orange", "QT加速信号", f"WALCL周环比减少{abs(metric.change_week):.0f}亿。"))


def _check_tga(metric: Metric | None, t: dict, alerts: list[Alert]) -> None:
    if not metric or metric.value is None:
        return
    if metric.value > t["tga_tight"]:
        alerts.append(Alert("orange", "TGA显著抽水", f"TGA余额{metric.value:.0f}亿，高于{t['tga_tight']:.0f}亿。"))
    if metric.change_week is not None and metric.change_week > t["tga_week_abs_alert"]:
        alerts.append(Alert("orange", "财政部快速重建现金", f"TGA周环比增加{metric.change_week:.0f}亿。"))
    if metric.change_week is not None and metric.change_week < -t["tga_week_abs_alert"]:
        alerts.append(Alert("green", "财政部释放流动性", f"TGA周环比下降{abs(metric.change_week):.0f}亿。"))


def _check_rrp(metric: Metric | None, t: dict, alerts: list[Alert]) -> None:
    if not metric or metric.value is None:
        return
    if metric.value < t["rrp_red"]:
        alerts.append(Alert("red", "RRP红色警戒", f"RRP余额{metric.value:.0f}亿，低于{t['rrp_red']:.0f}亿。"))
    elif metric.value < t["rrp_high_alert"]:
        alerts.append(Alert("orange", "RRP高度警报", f"RRP余额{metric.value:.0f}亿，低于{t['rrp_high_alert']:.0f}亿。"))
    if metric.change_1 is not None and metric.change_1 < t["rrp_day_drop_alert"]:
        alerts.append(Alert("orange", "RRP单日异常下降", f"RRP单日减少{abs(metric.change_1):.0f}亿。"))


def _check_reserves(metric: Metric | None, t: dict, alerts: list[Alert]) -> None:
    if not metric or metric.value is None:
        return
    if metric.value < t["reserves_red"]:
        alerts.append(Alert("red", "银行准备金接近最低舒适水平", f"准备金{metric.value / 10000:.2f}万亿。"))
    elif metric.value < t["reserves_watch"]:
        alerts.append(Alert("orange", "银行准备金进入警惕区", f"准备金{metric.value / 10000:.2f}万亿。"))


def _check_net(metric: Metric | None, t: dict, alerts: list[Alert]) -> None:
    if not metric or metric.change_week is None:
        return
    threshold = t["net_liquidity_week_abs_alert"]
    if metric.change_week > threshold:
        alerts.append(Alert("green", "净流动性大幅改善", f"周环比增加{metric.change_week:.0f}亿。"))
    elif metric.change_week < -threshold:
        alerts.append(Alert("orange", "净流动性快速恶化", f"周环比减少{abs(metric.change_week):.0f}亿。"))


def _check_sofr(sofr: Metric | None, spread: Metric | None, bp: dict, alerts: list[Alert]) -> None:
    if spread and spread.value is not None:
        if spread.value > bp["sofr_iorb_red"]:
            alerts.append(Alert("red", "SOFR-IORB利差红色警戒", f"利差{spread.value:.0f}bp。"))
        elif spread.value > bp["sofr_iorb_watch"]:
            alerts.append(Alert("orange", "SOFR-IORB利差警惕", f"利差{spread.value:.0f}bp。"))
        elif spread.value > bp["sofr_iorb_tight"]:
            alerts.append(Alert("yellow", "SOFR-IORB利差偏紧", f"利差{spread.value:.0f}bp。"))
    if sofr and sofr.change_1 is not None and sofr.change_1 > bp["sofr_day_jump_alert"]:
        alerts.append(Alert("red", "SOFR单日跳升", f"SOFR单日上行{sofr.change_1:.0f}bp。"))


def _check_dgs10(metric: Metric | None, bp: dict, alerts: list[Alert]) -> None:
    if metric and metric.change_1 is not None and abs(metric.change_1) > bp["dgs10_day_abs_alert"]:
        alerts.append(Alert("yellow", "10年美债收益率大幅波动", f"单日变动{metric.change_1:+.0f}bp。"))


def _base_level(metrics: dict[str, Metric], cfg: dict) -> str:
    t = cfg["thresholds_100m_usd"]
    bp = cfg["thresholds_bp"]
    net = metrics.get("net_liquidity")
    rrp = metrics.get("rrp")
    tga = metrics.get("tga")
    spread = metrics.get("sofr_iorb")

    red_hits = [
        rrp and rrp.value is not None and rrp.value < t["rrp_red"],
        spread and spread.value is not None and spread.value > bp["sofr_iorb_red"],
    ]
    if any(red_hits):
        return "red"

    orange_hits = [
        net and net.change_week is not None and net.change_week < -t["net_liquidity_week_abs_alert"],
        rrp and rrp.value is not None and rrp.value < t["rrp_high_alert"],
        tga and tga.value is not None and tga.value > t["tga_tight"],
        spread and spread.value is not None and spread.value > bp["sofr_iorb_watch"],
    ]
    if any(orange_hits):
        return "orange"

    green_hits = [
        net and net.change_week is not None and net.change_week > 0,
        rrp and rrp.value is not None and rrp.value > 3000,
        tga and tga.value is not None and tga.value < 7000,
        spread and spread.value is not None and spread.value < 3,
    ]
    if sum(1 for item in green_hits if item) >= 3:
        return "green"

    return "yellow"


def _strategy(level: str) -> str:
    return {
        "green": "风险资产顺风，可维持或小幅增加Beta敞口；继续观察TGA与RRP边际变化。",
        "yellow": "维持仓位，关注净流动性方向和RRP消耗速度；不建议忽视单日异常波动。",
        "orange": "流动性边际收紧，建议降低高Beta仓位、上移止损，并关注财政发债与回购市场压力。",
        "red": "危机预警区，建议大幅降低杠杆和高Beta敞口，等待政策或资金面修复信号。",
    }[level]
