"""Reproducible BTC negative-funding forward-return EVENT STUDY.

NOT a strategy backtest: no stop-loss, no position sizing, overlapping event
windows and simplified funding cashflows. Never interprets negative funding
as a trade recommendation or a verified edge.

Input: frozen public Binance USD-M BTCUSDT hourly OHLCV / settled funding.
Only data timestamped at or before each event may define its filter;
simulate entry at the *next hour OPEN* after the funding event hour.
"""
from __future__ import annotations

import argparse
import bisect
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HOUR = 3_600_000
START = datetime(2026, 5, 5, tzinfo=timezone.utc).timestamp() * 1000
TEST_START = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000
HORIZONS = (24, 72, 168)
COHORTS = ("all", "nonnegative", "negative", "negative_3",
           "negative_near_72h_low", "negative_sweep_bms_proxy", "negative_both")


def iso(timestamp_ms):
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def validate(data):
    assert data.get("schema") == "binance.usdm.btcsnapshot.1"
    assert data["market"] == "USD-M_PERPETUAL" and data["symbol"] == "BTCUSDT"
    bars, funds = data["klines"], data["funding"]
    if len(bars) < 1000 or len(funds) < 100:
        raise ValueError("Insufficient study data")
    for i, row in enumerate(bars):
        if len(row) != 6 or (i and row[0] - bars[i-1][0] != HOUR):
            raise ValueError("Hourly candles missing or not contiguous")
        _, op, hi, lo, cl, vol = row
        if not (lo <= op <= hi and lo <= cl <= hi and vol >= 0):
            raise ValueError("Invalid OHLCV")
    for i, item in enumerate(funds):
        if len(item) != 2 or (i and item[0] <= funds[i-1][0]):
            raise ValueError("Funding timestamps duplicate or unsorted")
    return bars, funds


def support_proxy(bars, last):
    """Within +1.2% / -0.5% of trailing 72h low, known at event time."""
    if last < 72:
        return False
    ref_low = min(x[3] for x in bars[last-72:last])
    cl = bars[last][4]
    return 0.995 * ref_low <= cl <= 1.012 * ref_low


def sweep_bms_proxy(bars, last):
    """A last-12h 20-bar sweep/reclaim followed by 3-bar pre-sweep high break.

    Explicitly NOT Strong MTF SR v3.3, Eric, or Pine V1.1 RTO parity.
    """
    if last < 40:
        return False
    for j in range(last-12, last):
        b = bars[j]
        prev = bars[j-20:j]
        prior_low = min(x[3] for x in prev)
        avg_volume = sum(x[5] for x in prev) / 20
        if not (b[3] < prior_low < b[4] and b[5] >= 0.8 * avg_volume):
            continue
        micro_high = max(x[2] for x in bars[j-3:j])
        following = bars[j+1:last+1]
        if any(x[3] <= b[3] for x in following):
            continue
        if any(x[4] > micro_high for x in following):
            return True
    return False


def costed_long(bars, funds, entry_index, hours, fee_per_side, slippage_per_side):
    """Fixed-horizon long: price return + approximate settled funding cashflow - costs."""
    if entry_index < 0 or entry_index + hours >= len(bars):
        return None
    entry, exit_ = bars[entry_index], bars[entry_index+hours]
    start, end = entry[0], exit_[0]
    if end - start != hours * HOUR:
        return None
    gross = exit_[1] / entry[1] - 1
    # Long receives when funding rate is negative. Approximate constant notional.
    received = -sum(rate for timestamp, rate in funds if start < timestamp < end)
    net = gross + received - 2 * (fee_per_side + slippage_per_side)
    return dict(entry_time=start, exit_time=end, gross=gross, funding_receipt=received, net=net)


def metrics(events):
    if not events:
        return dict(n=0)
    net = [x["net"] for x in events]
    positives = sum(x for x in net if x > 0)
    negatives = -sum(x for x in net if x < 0)
    return dict(n=len(events),
                mean_gross_pct=round(100 * statistics.mean(x["gross"] for x in events), 4),
                mean_net_pct=round(100 * statistics.mean(net), 4),
                median_net_pct=round(100 * statistics.median(net), 4),
                win_rate_pct=round(100 * sum(x > 0 for x in net)/len(net), 2),
                profit_factor=round(positives/negatives, 4) if negatives else None,
                mean_funding_receipt_pct=round(100*statistics.mean(x["funding_receipt"] for x in events), 5))


def no_overlap(events):
    """For correlated-event sensitivity; one hypothetical position at a time."""
    selected = []
    free_after = -1
    for ev in sorted(events, key=lambda x: x["entry_time"]):
        if ev["entry_time"] >= free_after:
            selected.append(ev)
            free_after = ev["exit_time"]
    return selected


def event_study(data, fee_per_side=0.0006, slippage_per_side=0.0002, *, start_ms=None, test_start_ms=None):
    bars, funds = validate(data)
    start_ms = START if start_ms is None else start_ms
    test_start_ms = TEST_START if test_start_ms is None else test_start_ms
    first_open = bars[0][0]
    groups = {h: {split: {key: [] for key in COHORTS} for split in ("train", "test")}
              for h in HORIZONS}
    for i, (event_time, rate) in enumerate(funds):
        if event_time < start_ms:
            continue
        # Last fully CLOSED candle known at settlement time. 1h delay before entry.
        last = (event_time - first_open) // HOUR - 1
        entry_index = int(last + 2)
        if last < 80 or entry_index >= len(bars):
            continue
        if bars[entry_index][0] <= event_time:
            raise ValueError("Entry would precede observed funding settlement")
        split = "train" if event_time < test_start_ms else "test"
        near_low = support_proxy(bars, int(last))
        bms = sweep_bms_proxy(bars, int(last))
        negative_3 = (i >= 2 and all(funds[k][1] < 0 for k in range(i-2, i+1)))
        for h in HORIZONS:
            outcome = costed_long(bars, funds, entry_index, h, fee_per_side, slippage_per_side)
            if outcome is None:
                continue
            outcome["signal_time"] = event_time
            bucket = groups[h][split]
            bucket["all"].append(outcome)
            if rate >= 0:
                bucket["nonnegative"].append(outcome)
            else:
                bucket["negative"].append(outcome)
                if negative_3:
                    bucket["negative_3"].append(outcome)
                if near_low:
                    bucket["negative_near_72h_low"].append(outcome)
                if bms:
                    bucket["negative_sweep_bms_proxy"].append(outcome)
                if near_low and bms:
                    bucket["negative_both"].append(outcome)
    summary = {}
    for horizon, splits in groups.items():
        summary[str(horizon)] = {}
        for split, cohorts in splits.items():
            summary[str(horizon)][split] = {
                name: {**metrics(events),
                       "nonoverlap": metrics(no_overlap(events))}
                for name, events in cohorts.items()
            }
    months = defaultdict(lambda: dict(total=0, negative=0))
    for timestamp, rate in funds:
        month = iso(timestamp)[:7]
        months[month]["total"] += 1
        if rate < 0:
            months[month]["negative"] += 1
    return dict(method="settled-funding-forward-long-event-study-v0.1",
                source=data["source"], market=data["market"], symbol=data["symbol"],
                fetched_at_utc=data["retrieved_at_utc"],
                candle_count=len(bars), settlement_count=len(funds),
                negative_settlements=sum(r < 0 for _, r in funds),
                candle_window=[iso(bars[0][0]), iso(bars[-1][0])],
                funding_window=[iso(funds[0][0]), iso(funds[-1][0])],
                study_start=iso(int(start_ms)), split_test_start=iso(int(test_start_ms)),
                horizon_hours=list(HORIZONS), fee_per_side=fee_per_side,
                slippage_per_side=slippage_per_side,
                monthly_funding_counts=dict(months), results=summary,
                limitations=[
                    "Event study, not a trading strategy; fixed-horizon positions without stop-loss.",
                    "Funding settlement known before next-hour-open entry; no future filter inputs.",
                    "Trading fee 0.06% per side and slippage 0.02% per side are hypothetical.",
                    "Funding receipt approximated using constant entry notional; not exact settlement mark PnL.",
                    "Overlapping entry events are correlated; nonoverlap subset is descriptive only.",
                    "72h support and sweep/BMS are simple proxies, not Pine v3.3/Eric/V1.1 parity.",
                    "Only ~May-Nov 2026 sample; no full market cycle or independent untouched OOS.",
                    "No robust confidence interval or causal inference; no proven profitable edge."
                ])


def report_markdown(result):
    lines = [
        "# BTCUSDT 负资金费率研究：历史事件检验 V0.1", "",
        f"数据源：{result['source']}；采集：{result['fetched_at_utc']}",
        f"样本：{result['candle_count']}根1小时K，"
        f"{result['settlement_count']}次已结算费率，其中{result['negative_settlements']}次负费率。",
        "研究区间：2026-05-05起，2026-09-01划分后段观察，7天持有期必须有完整未来数据。",
        "入场：资金费率结算后下一小时开盘；持有24/72/168小时后退出。",
        "净收益：开/平仓各0.06%费率+0.02%滑点，"
        "按固定名义仓位近似计入持仓期间已结算Funding。",
        "", "## 分组均值（净收益%：负值不代表策略历史可执行盈利）", "",
        "| 周期 | 时段 | 全部事件 N / 均值 | 费率非负 N / 均值 | 费率为负 N / 均值 | 负费率+72h低位 N / 均值 | 负费率+扫盘结构 N / 均值 |",
        "|---|---|---|---|---|---|---|"
    ]
    for h in ("24", "72", "168"):
        for split in ("train", "test"):
            s = result["results"][h][split]
            def v(key):
                d = s[key]
                return f"{d['n']} / {d.get('mean_net_pct', '—')}%"
            lines.append(f"| {h}h | {split} | {v('all')} | {v('nonnegative')} | {v('negative')} | {v('negative_near_72h_low')} | {v('negative_sweep_bms_proxy')} |")
    lines += ["", "## 7天窗口非重叠事件敏感性（仅描述，不是复利组合）", "",
              "| 时段 | 类别 | 全部N | 非重叠N | 非重叠均值净收益% |",
              "|---|---|---:|---:|---:|"]
    for split in ("train", "test"):
        for key in ("all", "nonnegative", "negative", "negative_near_72h_low"):
            d = result["results"]["168"][split][key]
            x = d["nonoverlap"]
            lines.append(f"| {split} | {key} | {d['n']} | {x['n']} | {x.get('mean_net_pct', '—')} |")
    lines += ["", "## 核心发现",
              "- 负费率并非自动买入信号：这段历史研究中负费率事件后的均值净收益未展示稳定正优势。",
              "- 支撑或扫盘过滤样本过少，无法声称组合有效；若交集为0则不可作组合收益结论。",
              "- 资金费率在交易系统里仍可作为高优先级的**逆向观察指标**，等待独立的价格结构验证。",
              "", "## 局限与下一步", *[f"- {x}" for x in result["limitations"]],
              "- 扩展跨周期历史；固定策略信号后验证独立样本；比较资金费率加入前后净收益与回撤。",
              ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Offline public BTC funding event study")
    p.add_argument("--data", default="research/data/binance_btcusdt_2026-05-01_to_2026-11-20.json")
    p.add_argument("--output-dir", default="output/study")
    args = p.parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    result = event_study(data)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/"funding_event_study.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (directory/"funding_event_study.md").write_text(report_markdown(result), encoding="utf-8")
    print(report_markdown(result))


if __name__ == "__main__":
    main()
