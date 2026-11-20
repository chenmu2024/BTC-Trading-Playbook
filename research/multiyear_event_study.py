"""Multi-year BTC settled funding event study; never an executable strategy.

Loads 2022-2026 frozen 1h BTCUSDT perpetual candles and funding records.
Train: 2022-2024, later historical: 2025-2026 (NOT untouched OOS).
Excludes train events whose holding periods cross the 2025 boundary.
"""
import argparse
import bisect
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from research.funding_event_study import HOUR, event_study, metrics, no_overlap

DIR = Path("research/data/multiyear")
FILENAMES = [f"btcusdt_{year}.json" for year in (2022,2023,2024,2025)]
FILENAMES += ["btcusdt_2026_through_2026-11-20.json"]
START_MS = int(datetime(2022,1,5,tzinfo=timezone.utc).timestamp()*1000)
SPLIT_MS = int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)


def load_years(directory=DIR):
    bars, funding, evidence = [], [], []
    for name in FILENAMES:
        p = Path(directory)/name
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("schema") != "binance.usdm.btcsnapshot.1" or d.get("symbol") != "BTCUSDT" or d.get("market") != "USD-M_PERPETUAL":
            raise ValueError("Incompatible archive: " + name)
        if not d.get("klines") or not d.get("funding"):
            raise ValueError("Empty archive: " + name)
        bars.extend(d["klines"])
        funding.extend(d["funding"])
        evidence.append({"file":name,"rows":len(d["klines"]),"settlements":len(d["funding"]),
                         "retrieved_at_utc":d.get("retrieved_at_utc")})
    for i,bar in enumerate(bars):
        if len(bar)!=6 or i and bar[0]-bars[i-1][0]!=HOUR:
            raise ValueError("Missing or duplicated hourly Kline at "+str(i))
    for i,record in enumerate(funding):
        if len(record)!=2 or i and record[0]<=funding[i-1][0]:
            raise ValueError("Non-monotonic settled funding at "+str(i))
    return {"schema":"binance.usdm.btcsnapshot.1","source":"Binance USD-M public API frozen annual snapshots",
            "market":"USD-M_PERPETUAL","symbol":"BTCUSDT",
            "retrieved_at_utc":evidence[-1]["retrieved_at_utc"],
            "klines":bars,"funding":funding}, evidence


def annual_summary(data, fees=0.0006, slippage=0.0002):
    bars,funds=data["klines"],data["funding"]
    times=[x[0] for x in funds]
    prefix=[0.0]
    for _,r in funds:
        prefix.append(prefix[-1]+r)
    first=bars[0][0]
    counts=defaultdict(lambda: {"total":0,"negative":0})
    group=defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for time,rate in funds:
        year=str(datetime.fromtimestamp(time/1000,timezone.utc).year)
        counts[year]["total"]+=1
        counts[year]["negative"]+=int(rate<0)
        last=int((time-first)//HOUR)-1
        entry=last+2
        if time<START_MS or last<80 or entry>=len(bars):
            continue
        if bars[entry][0]<=time:
            raise ValueError("Lookahead in entry")
        for h in (24,72,168):
            exit_=entry+h
            if exit_>=len(bars):
                continue
            # Don't let a training event's P&L use 2025 holdout prices.
            if time<SPLIT_MS and bars[exit_][0]>=SPLIT_MS:
                continue
            a,b=bars[entry],bars[exit_]
            if b[0]-a[0]!=h*HOUR:raise ValueError("Noncontiguous hold")
            lo=bisect.bisect_right(times,a[0])
            hi=bisect.bisect_left(times,b[0])
            paid=-(prefix[hi]-prefix[lo])
            gross=b[1]/a[1]-1
            event={"entry_time":a[0],"exit_time":b[0],"gross":gross,
                   "funding_receipt":paid,"net":gross+paid-2*(fees+slippage)}
            group[year][str(h)]["negative" if rate<0 else "nonnegative"].append(event)
    return {
      "counts":dict(counts),
      "returns":{year:{h:{label:{**metrics(events),"nonoverlap":metrics(no_overlap(events))}
                         for label,events in labels.items()} for h,labels in horizons.items()}
                 for year,horizons in group.items()}
    }


def research(directory=DIR):
    data,evidence=load_years(directory)
    sample=event_study(data,start_ms=START_MS,test_start_ms=SPLIT_MS,strict_split_end=True)
    return {"study":"multi_year_negative_funding_events_v0.2","status":"RESEARCH_ONLY",
            "years":"2022-2026 (through Nov 20)",
            "candle_count":len(data["klines"]),
            "settlement_count":len(data["funding"]),
            "first_hour":datetime.fromtimestamp(data["klines"][0][0]/1000,timezone.utc).isoformat(),
            "last_hour":datetime.fromtimestamp(data["klines"][-1][0]/1000,timezone.utc).isoformat(),
            "archive_evidence":evidence,
            "train_vs_later":sample,
            "annual":annual_summary(data),
            "limits":["Fixed-horizon returns are an event study not stop-loss/RTO trading strategy",
                      "Funding credit is constant-notional approximation; transaction costs assumed",
                      "Overlapping settlement event windows are dependent; nonoverlap is a check",
                      "Cohorts called near_low or sweep_bms are research proxies, NOT strong SR v3.3 or Pine V1.1",
                      "2025-2026 is later historical, not genuinely unseen out-of-sample data"]}


def markdown(r):
    lines=["# BTCUSDT负资金费率2022—2026跨周期事件研究",
           "",f"历史K线：{r['candle_count']:,}；结算：{r['settlement_count']:,}。",
           f"时间窗：{r['first_hour']} 至 {r['last_hour']}。",
           "规则：已结算费率后一小时开盘做多，24h/72h/7天退出；费用0.06%每边手续费+0.02%每边滑点；含固定名义仓位Funding近似。",
           "2022—2024早段与2025—2026后段分开，持有跨越分界的早段样本已剔除。",
           "", "| 年份 | Funding次数 | 负费率次数 | 负值占比 |",
           "|---|---:|---:|---:|"]
    for year, d in r["annual"]["counts"].items():
        lines.append(f"| {year} | {d['total']} | {d['negative']} | {100*d['negative']/d['total']:.1f}% |")
    lines += ["", "## 年度比较（平均净回报% / 样本数）","",
              "| 年份 | 持有期 | 非负Funding做多 | 负Funding做多 | 负Funding不重叠样本 |",
              "|---|---|---|---|---|"]
    for year,hrs in r["annual"]["returns"].items():
        for h in ("24","72","168"):
            x=hrs.get(h,{})
            def val(k):
                z=x.get(k,{"n":0})
                return f"{z.get('mean_net_pct','—')}% / {z['n']}"
            neg=x.get("negative",{})
            no=neg.get("nonoverlap",{})
            lines.append(f"| {year} | {h}h | {val('nonnegative')} | {val('negative')} | {no.get('mean_net_pct','—')}% / {no.get('n',0)} |")
    lines += ["","## 早段 / 后段分组（重叠事件，不是独立交易）", "",
              "| 时段 | 持有 | 非负Funding N / 净均值% | 负Funding N / 净均值% | 负Funding+低位代理 N / 净均值% |",
              "|---|---|---|---|---|"]
    for split in ("train","test"):
        for h in ("24","72","168"):
            d=r["train_vs_later"]["results"][h][split]
            def val(k):
                z=d[k]
                return f"{z['n']} / {z.get('mean_net_pct','—')}"
            lines.append(f"| {split} | {h}h | {val('nonnegative')} | {val('negative')} | {val('negative_near_72h_low')} |")
    lines += ["","## 研究边界",""]
    lines += ["- "+x for x in r["limits"]]
    lines += ["","**不得直接把负Funding分类当成多头入场信号，也不能将上述均值解释为真实策略净值。**",""]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-dir",default=str(DIR))
    p.add_argument("--output-dir",default="output/multiyear")
    args=p.parse_args()
    report=research(args.data_dir)
    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"multiyear_funding.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"multiyear_funding.md").write_text(markdown(report),encoding="utf-8")
    print(markdown(report))


if __name__=="__main__":
    main()
