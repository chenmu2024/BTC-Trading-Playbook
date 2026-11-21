"""Five-step BTCUSD-M strategy research: objective backtest of observable steps.

This is NOT exact TradingView Strong SR v3.3, Eric 1.9.10, or V1.1 parity.
Historical archive has hourly OHLCV and settled funding, but no 5-year OI,
true taker-side CVD, or archived historical Pine event states. Unobserved
conditions remain UNKNOWN rather than being invented.
"""
from __future__ import annotations
import argparse
import bisect
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from research.multiyear_event_study import load_years

HOUR=3600000
CUT=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)
FEE=0.0006
SLIP=0.0002
RISK_TREND=0.005
RISK_RANGE=0.0025
CAP=0.95
COOLDOWN=8
HOLD=48

@dataclass(frozen=True)
class Variant:
    name: str
    context: str
    phase: str
    funding: str
    require_zone: bool=False

VARIANTS=(
    Variant("A_BMS","A","BMS","ANY"),
    Variant("A_RTO","A","RTO","ANY"),
    Variant("A_RTO_FUND","A","RTO","CONTRARIAN"),
    Variant("A_RTO_ZONE","A","RTO","ANY",True),
    Variant("A_RTO_ZONE_FUND","A","RTO","CONTRARIAN",True),
    Variant("B_RTO","B","RTO","ANY"),
    Variant("B_RTO_FUND","B","RTO","CONTRARIAN"),
    Variant("B_RTO_STREAK3","B","RTO","STREAK3",True),
)

def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()

def ema(values,n):
    out=[None]*len(values)
    if len(values)<n:return out
    x=sum(values[:n])/n
    out[n-1]=x
    a=2/(n+1)
    for i in range(n,len(values)):
        x=x+a*(values[i]-x)
        out[i]=x
    return out

def hourly_atr(bars,n=14):
    tr=[]
    for i,b in enumerate(bars):
        prior=b[4] if i==0 else bars[i-1][4]
        tr.append(max(b[2]-b[3],abs(b[2]-prior),abs(b[3]-prior)))
    r=[None]*len(bars)
    if len(bars)<n:return r
    v=sum(tr[:n])/n
    r[n-1]=v
    for i in range(n,len(bars)):
        v=(v*(n-1)+tr[i])/n
        r[i]=v
    return r

def htf(bars,hours):
    """At bar i open, access 1D/4H bar at j=i//hours-1 ONLY."""
    if bars[0][0]%(HOUR*hours):
        raise ValueError("Nonaligned UTC history")
    h=[]
    for i in range(0,len(bars)-hours+1,hours):
        b=bars[i:i+hours]
        h.append([b[0][0],b[-1][4],max(x[2] for x in b),min(x[3] for x in b)])
    e50=ema([x[1] for x in h],50)
    e200=ema([x[1] for x in h],200)
    status=[]
    for i,bar in enumerate(h):
        s=0
        if e200[i] is not None:
            if bar[1]>e50[i]>e200[i]:s=1
            if bar[1]<e50[i]<e200[i]:s=-1
        # 4h support/resistance from the last 20 COMPLETED 4h bars
        low=min(x[3] for x in h[i-20:i]) if i>=20 else None
        high=max(x[2] for x in h[i-20:i]) if i>=20 else None
        status.append((s,low,high))
    return [status[i//hours-1] if i//hours>0 else (0,None,None)
            for i in range(len(bars))]

def generate_signals(bars,funds):
    """No lookahead: 1h sweep->BMS within 5->optional RTO within 5."""
    atr=hourly_atr(bars)
    day=htf(bars,24)
    four=htf(bars,4)
    fts=[x[0] for x in funds]
    volume_prefix=[0]
    for b in bars:volume_prefix.append(volume_prefix[-1]+b[5])
    states={1:None,-1:None}
    events=[]
    counters=defaultdict(int)
    # Need 200 COMPLETED daily candles for EMA200.
    for i in range(24*201,len(bars)-1):
        op,hi,lo,cl,vol=bars[i][1:]
        a=atr[i]
        if a is None or a<=0:continue
        for side in (1,-1):
            st=states[side]
            if st:
                invalid=lo<=st["extreme"] if side==1 else hi>=st["extreme"]
                timeout=(i-st["sweep_i"]>5 if st["stage"]==1
                         else i-st["bms_i"]>5)
                if invalid or timeout:
                    states[side]=None
                    counters["invalidated"]+=1
                elif st["stage"]==1 and i>st["sweep_i"]:
                    ok=(cl>st["bms_level"] and cl>op if side==1
                        else cl<st["bms_level"] and cl<op)
                    if ok and abs(cl-op)>=0.2*a:
                        counters["BMS_LONG" if side==1 else "BMS_SHORT"]+=1
                        st["stage"]=2
                        st["bms_i"]=i
                        events.append((i,side,"BMS",st.copy()))
                elif st["stage"]==2 and i>st["bms_i"]:
                    level=st["bms_level"]
                    ok=(lo<=level+0.15*a and lo>=level-0.35*a and cl>level and cl>op
                        if side==1 else hi>=level-0.15*a and hi<=level+0.35*a and cl<level and cl<op)
                    if ok:
                        counters["RTO_LONG" if side==1 else "RTO_SHORT"]+=1
                        events.append((i,side,"RTO",st.copy()))
                        states[side]=None
            if states[side]:continue
            last=bars[i-20:i]
            ref=min(b[3] for b in last) if side==1 else max(b[2] for b in last)
            vmean=(volume_prefix[i]-volume_prefix[i-20])/20
            rng=hi-lo
            wick=(min(op,cl)-lo if side==1 else hi-max(op,cl))/rng if rng>0 else 0
            swept=(lo<ref-0.1*a and cl>ref+0.05*a if side==1
                   else hi>ref+0.1*a and cl<ref-0.05*a)
            if not (swept and wick>=0.3 and vol>=vmean and vmean>0):continue
            counters["SWEEP_LONG" if side==1 else "SWEEP_SHORT"]+=1
            zone=four[i][1 if side==1 else 2]
            extreme=lo if side==1 else hi
            bms=max(hi,max(b[2] for b in bars[i-3:i])) if side==1 else min(lo,min(b[3] for b in bars[i-3:i]))
            states[side]={"stage":1,"sweep_i":i,"extreme":extreme,
                          "sweep_atr":a,"bms_level":bms,
                          "near_zone":zone is not None and abs(extreme-zone)<=1.5*a}
    for i,side,phase,st in events:
        daily=day[i][0]
        fourhr=four[i][0]
        a_context=(daily==side and fourhr==side)
        b_context=(not a_context and st["near_zone"])
        fi=bisect.bisect_left(fts,bars[i][0])-1  # strictly prior settlement
        rate=funds[fi][1] if fi>=0 and bars[i][0]-fts[fi]<=16*HOUR else None
        streak=(rate is not None and fi>=2 and
                (all(funds[k][1]<0 for k in (fi-2,fi-1,fi+1)) if side==1
                 else all(funds[k][1]>0 for k in (fi-2,fi-1,fi+1))))
        yield {"signal_index":i,"side":side,"phase":phase,"A":a_context,"B":b_context,
               "zone":st["near_zone"],"extreme":st["extreme"],"sweep_atr":st["sweep_atr"],
               "bms_level":st["bms_level"],"atr":atr[i],
               "trend_day":daily,"trend_4h":fourhr,
               "funding_rate":rate,"funding_streak3":streak}
    generate_signals.counts=dict(counters)

def matches(signal,variant):
    if signal["phase"]!=variant.phase or not signal[variant.context]:return False
    if variant.require_zone and not signal["zone"]:return False
    if variant.funding=="ANY":return True
    rate=signal["funding_rate"]
    contra=rate is not None and rate*signal["side"]<0
    if variant.funding=="CONTRARIAN":return contra
    return contra and signal["funding_streak3"]

def fill(signal,bars,funds,ftimes,prefix,equity,risk):
    """Next 1H open with adverse slippage; conservative stop-first rule."""
    i=signal["signal_index"]+1
    # Reject incomplete 48h observation windows instead of silently
    # shortening the final trade when the archive ends.
    if i+HOLD>len(bars):return None
    side=signal["side"]
    entry=bars[i][1]*(1+side*SLIP)
    stop=signal["extreme"]-side*0.20*signal["sweep_atr"]
    distance=side*(entry-stop)
    if distance<=0 or not 0.25*signal["atr"]<=distance<=3.0*signal["atr"]:return None
    qty=min(risk*equity/distance,CAP*equity/entry)
    target=entry+side*2.0*distance
    last=min(len(bars)-1,i+48-1)
    exit_i=last
    kind="TIME"
    price=bars[last][4]
    for k in range(i,last+1):
        o,hi,lo=bars[k][1:4]
        if side==1:
            if o<=stop:exit_i=k;price=o;kind="GAP_STOP";break
            if lo<=stop:exit_i=k;price=stop;kind="STOP";break
            if hi>=target:exit_i=k;price=target;kind="TARGET";break
        else:
            if o>=stop:exit_i=k;price=o;kind="GAP_STOP";break
            if hi>=stop:exit_i=k;price=stop;kind="STOP";break
            if lo<=target:exit_i=k;price=target;kind="TARGET";break
    actual_exit=price*(1-side*SLIP)
    raw_pnl=qty*side*(actual_exit-entry)
    fee=FEE*qty*(entry+actual_exit)
    # Funding paid/received before EXIT HOUR starts, not ambiguous exit-bar events.
    fstart=bisect.bisect_right(ftimes,bars[i][0])
    fend=bisect.bisect_left(ftimes,bars[exit_i][0])
    funding=-side*(prefix[fend]-prefix[fstart])*qty*entry
    pnl=raw_pnl-fee+funding
    adverse=min(b[3] for b in bars[i:exit_i+1]) if side==1 else max(b[2] for b in bars[i:exit_i+1])
    if kind=="STOP":
        adverse=max(adverse,stop) if side==1 else min(adverse,stop)
    worst=equity+qty*side*(adverse-entry)-FEE*qty*entry
    return {**signal,"entry_index":i,"exit_index":exit_i,"entry_time":bars[i][0],
            "exit_time":bars[exit_i][0]+HOUR,"entry":entry,"exit":actual_exit,
            "stop":stop,"target":target,"qty":qty,"type":kind,
            "fee_cash":fee,"funding_cash":funding,"price_cash":raw_pnl,
            "pnl":pnl,"pnl_pct":100*pnl/equity,"equity_after":equity+pnl,
            "worst_intratrade_equity":worst}

def simulate(events,bars,funds,variant,split):
    times=[r[0] for r in funds]
    prefix=[0.0]
    for _,rate in funds:prefix.append(prefix[-1]+rate)
    start=bars[0][0] if split=="2022_2024" else CUT
    end=CUT if split=="2022_2024" else 10**18
    equity=10000.0;peak=equity;dd=0.0;last_exit=-100
    selected=[];considered=0;geometry=0;cooldowns=0
    for signal in events:
        if not matches(signal,variant):continue
        i=signal["signal_index"]+1
        if i>=len(bars) or not start<=bars[i][0]<end:continue
        # Lock all potential maximum-hold candles inside the split; do not
        # select favorable early exits while dropping unfavorable late exits.
        if bars[i][0]+HOLD*HOUR>end:continue
        considered+=1
        if i<=last_exit+COOLDOWN:cooldowns+=1;continue
        result=fill(signal,bars,funds,times,prefix,equity,
                    RISK_TREND if variant.context=="A" else RISK_RANGE)
        if result is None:geometry+=1;continue
        if result["exit_time"]>end:continue
        dd=max(dd,100*max(0,peak-result["worst_intratrade_equity"])/peak)
        equity=result["equity_after"]
        dd=max(dd,100*max(0,peak-equity)/peak)
        peak=max(equity,peak)
        last_exit=result["exit_index"]
        selected.append(result)
    wins=[v["pnl"] for v in selected if v["pnl"]>0]
    losses=[-v["pnl"] for v in selected if v["pnl"]<0]
    # Side breakdown is a subset of the same single-position equity path;
    # side-only returns are NOT independent portfolio equity curves.
    by_side={}
    for direction,label in ((1,"LONG"),(-1,"SHORT")):
        group=[t for t in selected if t["side"]==direction]
        win=[t["pnl"] for t in group if t["pnl"]>0]
        loss=[-t["pnl"] for t in group if t["pnl"]<0]
        by_side[label]={"count":len(group),
                        "wins":len(win),
                        "win_rate_pct":round(100*len(win)/len(group),2) if group else None,
                        "profit_factor":round(sum(win)/sum(loss),4) if loss else None,
                        "avg_trade_equity_pct":round(sum(t["pnl_pct"] for t in group)/len(group),4) if group else None,
                        "sum_net_pnl_usdt":round(sum(t["pnl"] for t in group),2)}
    return {"variant":variant.name,"split":split,"trades":len(selected),
            "by_side":by_side,
            "eligible_signals":considered,"rejected_stop_distance":geometry,
            "overlap_or_cooldown":cooldowns,
            "win_rate_pct":round(100*len(wins)/len(selected),2) if selected else None,
            "profit_factor":round(sum(wins)/sum(losses),4) if losses else None,
            "return_pct":round(100*(equity/10000-1),4),
            "avg_net_trade_equity_pct":round(sum(v["pnl_pct"] for v in selected)/len(selected),4) if selected else None,
            "max_intratrade_drawdown_pct":round(dd,4),
            "ending_equity_usdt":round(equity,2),
            "funding_cash":round(sum(v["funding_cash"] for v in selected),2),
            "stops":sum(t["type"] in ("STOP","GAP_STOP") for t in selected),
            "targets":sum(t["type"]=="TARGET" for t in selected),
            "trade_details":selected}

def research(data):
    bars,funds=data["klines"],data["funding"]
    if len(bars)<40000 or len(funds)<5000:raise ValueError("Insufficient historical archive")
    signals=list(generate_signals(bars,funds))
    results=[simulate(signals,bars,funds,v,split)
             for v in VARIANTS for split in ("2022_2024","2025_2026")]
    return {"model":"Five-step observable subset V0.1; NOT original Pine parity",
            "status":"RESEARCH_ONLY",
            "bars":len(bars),"funding_records":len(funds),
            "period":[iso(bars[0][0]),iso(bars[-1][0])],
            "cutover":iso(CUT),
            "sweep_counts":generate_signals.counts,"signal_count":len(signals),
            "fees_per_side":FEE,"slippage_per_side":SLIP,
            "not_available":["historical tick CVD","historical OI","original Eric states",
                             "original SR v3.3 levels","historic SPX/DXY/gold regime"],
            "caveats":["Exploratory parameter variations over previously inspected history, not untouched OOS",
                       "Only 1h OHLCV + settled funding; 1D/4H structure and 4H zone are explicit proxies",
                       "Intrabar order unknown; stop takes priority over target",
                       "Cashflow uses entry-notional funding approximation and omits exit-hour ambiguity",
                       "Closed equity and conservative low/high intrabar DD model; no mark-price liquidation",
                       "Each variant uses own independent account; never sum variant equity curves"],
            "results":[{k:v for k,v in x.items() if k!="trade_details"} for x in results],
            "trades":{x["variant"]+"__"+x["split"]:x["trade_details"] for x in results}}

def markdown(r):
    lines=["# BTC 2022—2026 五步交易历史回测｜可观测条件版本","",
           f"市场：Binance BTCUSDT USD-M 永续；{r['bars']} 根1小时K；{r['funding_records']} 次结算；{r['period']}.",
           "A：严格1D+4H EMA同向顺势；B：非同向且接近前20根已完成4H区间边缘。多空对称。",
           "流动性：前20小时高低；扫盘收回→5根内BMS→可选5根内RTO；成交量≥前20根均量。",
           "下一根1H开盘成交、单仓与8K冷却；顺势每笔0.5%、逆势0.25%风险，名义敞口≤95%，2R、48小时退出。",
           "手续费每边0.06%+不利滑点每边0.02%；资金费率在已结算可知的时点过滤并计入模拟现金流。",
           "**尚不包含真实CVD/OI、原SR v3.3区域、Eric 1.9.10 反转背离。不得称为原指标完整回测。**","",
           "| 模型 | 区间 | 合格信号 | 交易数 | 胜率% | PF | 净收益% | 保守最大浮动回撤% |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in r["results"]:
        f=lambda k: x[k] if x[k] is not None else "—"
        lines.append(f"| {x['variant']} | {x['split']} | {x['eligible_signals']} | {x['trades']} | {f('win_rate_pct')} | {f('profit_factor')} | {x['return_pct']} | {x['max_intratrade_drawdown_pct']} |")
    lines+=["","## 核心模型的多头/空头分项（同一净值路径的交易子集）","",
           "| 模型 | 区间 | 方向 | 笔数 | 胜率% | PF | 平均每笔权益收益% |",
           "|---|---|---|---:|---:|---:|---:|"]
    for x in r["results"]:
        if x["variant"] not in ("A_BMS","A_RTO","B_RTO","B_RTO_FUND"):continue
        for direction,entry in x["by_side"].items():
            fmt=lambda v: "—" if v is None else str(v)
            lines.append(f"| {x['variant']} | {x['split']} | {direction} | {entry['count']} | {fmt(entry['win_rate_pct'])} | {fmt(entry['profit_factor'])} | {fmt(entry['avg_trade_equity_pct'])} |")
    lines+=["","## 边界与缺失",""]+["- "+x for x in r["caveats"]]
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-dir",default="research/data/multiyear")
    p.add_argument("--output-dir",default="output/five_step")
    args=p.parse_args()
    data,_=load_years(args.data_dir)
    r=research(data)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"report.md").write_text(markdown(r),encoding="utf-8")
    with open(out/"trades.csv","w",newline="",encoding="utf-8") as file:
        w=csv.writer(file)
        w.writerow(["variant","side","signal_utc","entry_utc","exit_utc","entry","stop",
                    "target","exit","size","reason","fees","funding_cash","pnl","equity_after"])
        for variant,trades in r["trades"].items():
            for t in trades:
                w.writerow([variant,"LONG" if t["side"]==1 else "SHORT",
                 iso(data["klines"][t["signal_index"]][0]+HOUR),iso(t["entry_time"]),
                 iso(t["exit_time"]),t["entry"],t["stop"],t["target"],t["exit"],
                 t["qty"],t["type"],t["fee_cash"],t["funding_cash"],t["pnl"],t["equity_after"]])
    print(markdown(r))

if __name__=="__main__":
    main()
