# 美元流动性预警监控

这是一个轻量版美元流动性监控器，会抓取 FRED、Treasury Daily Statement 的公开数据，计算综合预警等级，并推送到 Discord Webhook。

## 已实现

- WALCL、TGA、RRP、银行准备金、SOFR、IORB、10年/2年美债等核心指标
- 净流动性计算: `WALCL - TGA - RRP`
- 绿色、黄色、橙色、红色综合等级
- 阈值事件预警
- Discord Webhook 推送
- SQLite 保存历史快照
- GitHub Actions 工作日定时运行

## 建议后续增强

- 接入 SPX 数据，做净流动性和标普500背离提醒
- 增加 90 日 Z-score 异常检测
- 接入 FOMC 日历，在会议前后提高提示权重
- 若要做 Qt 桌面端，可把 `collect_metrics()` 作为后端，前端用 PySide6 展示仪表盘

## 本地运行

安装依赖:

```bash
python -m pip install -r liquidity_monitor/requirements.txt
```

当前版本只使用 Python 标准库，这一步主要是为了兼容后续扩展。

先预览，不推送:

```bash
python -m liquidity_monitor.main --preview
```

推送到 Discord:

```bash
copy liquidity_monitor\config\secrets.env.example liquidity_monitor\config\secrets.env
```

编辑 `liquidity_monitor/config/secrets.env`:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
FRED_API_KEY=
```

然后运行:

```bash
python -m liquidity_monitor.main
```

`FRED_API_KEY` 可选。没填时会使用 FRED 公开 CSV；填了则使用官方 API。

## GitHub Actions 部署

仓库里已经包含 `.github/workflows/liquidity-monitor.yml`。

在 GitHub 仓库设置里添加 Secrets:

- `DISCORD_WEBHOOK_URL`: 必填
- `FRED_API_KEY`: 可选

默认工作日 UTC 21:00 自动运行，也可以在 Actions 页面手动触发。

## 调整阈值

所有预警阈值都在:

```text
liquidity_monitor/config/thresholds.yaml
```

单位说明:

- 资金量阈值使用“亿美元”
- 利率利差阈值使用“bp”

## 数据口径说明

- TGA 优先抓取 Treasury Daily Statement 的 `Treasury General Account (TGA) Closing Balance`。
- 如果 DTS 只返回旧口径 `Federal Reserve Account`，会在日报的“数据核验”里标明。
- 如果 DTS 与 FRED `WTREGEN` 差异超过 1000 亿，净流动性计算会采用 FRED 值，并提示核对 DTS 字段和单位。
- DTS 官方说明中 Operating Cash Balance 数字按“百万美元”四舍五入；程序显示时统一换算为“亿美元”。
- FRED 的 WALCL、WTREGEN、WRESBAL 通常是“百万美元”口径；RRPONTSYD 是“十亿美元”口径，程序会单独乘以 10 换算为“亿美元”。
