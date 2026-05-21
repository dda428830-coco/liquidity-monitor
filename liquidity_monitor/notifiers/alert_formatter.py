from __future__ import annotations

from datetime import date

from liquidity_monitor.analyzers.liquidity_calc import Metric
from liquidity_monitor.analyzers.threshold_check import Assessment


def format_report(metrics: dict[str, Metric], assessment: Assessment, cfg: dict) -> str:
    level = cfg["levels"][assessment.level]
    today = date.today().isoformat()
    lines = [
        f"📊 美元流动性日报 [{today}]",
        "",
        f"🔵 综合等级:{level['emoji']} {level['name']}({level['label']})",
        "",
        "📈 核心数据:",
        f"• 美联储总资产:{_money(metrics.get('walcl'), trillion=True)}{_change(metrics.get('walcl'), '周环比')}",
        f"• TGA余额:{_money(metrics.get('tga'))}{_change(metrics.get('tga'), '周/近似环比')}",
        f"• RRP余额:{_money(metrics.get('rrp'))}{_avg5(metrics.get('rrp'))}{_change(metrics.get('rrp'), '日环比')}",
        f"• 银行准备金:{_money(metrics.get('reserves'), trillion=True)}",
        f"• SOFR:{_rate(metrics.get('sofr'))}{_date_tag(metrics.get('sofr'))} (IORB利差 {_bp_value(metrics.get('sofr_iorb'))}{_date_tag(metrics.get('sofr_iorb'))})",
        f"• 10年美债:{_rate(metrics.get('dgs10'))}",
        "",
        f"💧 净流动性:{_money(metrics.get('net_liquidity'), trillion=True)}{_change(metrics.get('net_liquidity'), '周环比')}",
        "",
        "⚠️ 触发预警:",
    ]

    if assessment.alerts:
        lines.extend(f"• {alert.title}: {alert.detail}" for alert in assessment.alerts[:8])
    else:
        lines.append("• 暂无阈值突破。")

    if assessment.data_warnings:
        lines.extend(["", "🧪 数据核验:"])
        lines.extend(f"• {warning}" for warning in assessment.data_warnings[:6])

    lines.extend(
        [
            "",
            "💡 策略提示:",
            assessment.strategy,
            "",
            "🔗 数据来源:FRED / Treasury Daily Statement",
        ]
    )
    return "\n".join(lines)


def _money(metric: Metric | None, trillion: bool = False) -> str:
    if not metric or metric.value is None:
        return "缺失"
    if trillion:
        return f"${metric.value / 10000:.2f}万亿"
    return f"${metric.value:.0f}亿"


def _change(metric: Metric | None, label: str) -> str:
    if not metric:
        return ""
    change = metric.change_1 if "日" in label else metric.change_week
    if change is None:
        return ""
    arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    return f"({label} {change:+.0f}亿){arrow}"


def _avg5(metric: Metric | None) -> str:
    if not metric or metric.avg_5 is None:
        return ""
    return f"(5日均值 {metric.avg_5:.0f}亿)"


def _rate(metric: Metric | None) -> str:
    if not metric or metric.value is None:
        return "缺失"
    return f"{metric.value:.2f}%"


def _bp_value(metric: Metric | None) -> str:
    if not metric or metric.value is None:
        return "缺失"
    return f"{metric.value:+.0f}bp"


def _date_tag(metric: Metric | None) -> str:
    if not metric or metric.date is None:
        return ""
    return f"[{metric.date.isoformat()}]"
