"""A conservative BTC long-only SH → BMS → optional RTO proxy backtest.

DOES NOT reproduce original Pine v1.1, Strong MTF SR v3.3 or Eric:
- ATR is Wilder RMA from hourly data; Pine may compute differently.
- "confirmed 4h support" is a distinct delayed double-pivot PROXY.
- No authentic Footprint, CVD, OI or original Eric statuses.
- Stop-first if both TP and SL fall inside the same hourly candle.
- Entries at next completed-signal bar OPEN, fees/slippage, funding included.
- This research script never connects to trading accounts or sends orders.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from research.funding_event_study import HOUR, metrics, no_overlap
from research.mtf_support_proxy import confirmed_support_zones, near_confirmed_support, wilder_atr
from research.multiyear_event_study import load_years, SPLIT_MS

GROUPS=("all","negative","nonnegative","negative_near_72h_low",
        "negative_confirmed_4h_proxy","negative_both")
PHASES=("BMS_break","BMS_RTO")
# Frozen experiment settings, not optimized performance parameters.
LIQ_LOOKBACK=20
MICRO_LOOKBACK=3
VOL_LOOKBACK=20
CONFIRM_BARS=5
RETEST_BARS=5
REWARD_R=2.0
MAX_HOLD_BARS=48
STOP_ATR_BUFFER=0.20
FEE_PER_SIDE=0.0006
SLIPPAGE_PER_SIDE=0.0002


def iso(t):
    return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()


def near_previous_low(bars, index, price, lookback=72):
    if index<lookback:
        return False
    prior=min(bars[k][3] for k in range(index-lookback,index))
    return 0.995*prior<=price<=1.012*prior


def generate_causal_long_setups(bars, funds):
    """Completed hourly bars only; never use future candles to create a setup."""
    dat=[{"high":r[2],"low":r[3],"close":r[4]} for r in bars]
    atr=wilder_atr(dat)
    zones=confirmed_support_zones(bars)
    ftime=[x[0] for x in funds]
    state=None
    observed=[]
    stats={"sweeps":0,"bms":0,"rto":0,"confirmed_4h_proxy_zones":len(zones)}
    for i in range(max(80,LIQ_LOOKBACK+VOL_LOOKBACK),len(bars)-1):
        bar=bars[i]
        op,hi,lo,cl,vol=bar[1:]
        a=atr[i]
        if a is None or a<=0:
            continue
        if state is not None:
            age=i-state["sweep_bar"]
            invalid=lo<=state["sweep_extreme"]
            timeout=(age>CONFIRM_BARS if state["phase"]==1
                     else i-state["break_bar"]>RETEST_BARS)
            if invalid or timeout:
                state=None
            elif state["phase"]==1 and i>state["sweep_bar"]:
                body=cl-op
                if cl>state["bms_level"] and body>=0.2*a:
                    stats["bms"]+=1
                    observed.append(make_signal(i,state,bars,funds,ftime,"BMS_break",a))
                    state["phase"]=2
                    state["break_bar"]=i
            elif state["phase"]==2 and i>state["break_bar"]:
                level=state["bms_level"]
                if (lo<=level+0.15*a and lo>=level-0.35*a
                        and cl>level and cl>op):
                    stats["rto"]+=1
                    observed.append(make_signal(i,state,bars,funds,ftime,"BMS_RTO",a))
                    state=None
        if state is None:
            prev=bars[i-LIQ_LOOKBACK:i]
            prior_low=min(x[3] for x in prev)
            average=sum(x[5] for x in bars[i-VOL_LOOKBACK:i])/VOL_LOOKBACK
            candle_range=hi-lo
            wick=((min(op,cl)-lo)/candle_range if candle_range>0 else 0.0)
            if (average>0 and vol>=average and wick>=0.30 and
                    lo<prior_low-0.10*a and cl>prior_low+0.05*a):
                stats["sweeps"]+=1
                state={"phase":1,"sweep_bar":i,"sweep_extreme":lo,
                       "bms_level":max(hi,max(x[2] for x in bars[i-MICRO_LOOKBACK:i])),
                       "sweep_atr":a,"near_low":near_previous_low(bars,i,cl),
                       "near_4h":near_confirmed_support(zones,i,lo,a)}
    return observed,stats


def make_signal(index,state,bars,funds,ftime,phase,atr_now):
    """Funding known at the BEGINNING of the signal bar (1h publication lag)."""
    stamp=bars[index][0]
    j=bisect.bisect_left(ftime,stamp)-1
    valid=j>=0 and stamp-ftime[j]<=16*HOUR
    rate=funds[j][1] if valid else None
    streak=valid and j>=2 and all(funds[k][1]<0 for k in (j-2,j-1,j))
    return {"confirm_idx":index,"confirm_utc":iso(bars[index][0]+HOUR),
            "phase":phase,"sweep_idx":state["sweep_bar"],
            "sweep_atr":state["sweep_atr"],"atr_entry_basis":atr_now,
            "sweep_extreme":state["sweep_extreme"],
            "bms_level":state["bms_level"],"near_low":state["near_low"],
            "near_confirmed_4h_proxy":state["near_4h"],
            "funding_rate_fraction":rate,
            "funding_streak_negative3":bool(streak)}


def simulate_long(signal,bars,funds,ftimes,prefix, *,
                  max_hold=MAX_HOLD_BARS,rr=REWARD_R):
    entry_i=signal["confirm_idx"]+1
    if entry_i>=len(bars):
        return None
    entry=bars[entry_i][1]
    stop=signal["sweep_extreme"]-STOP_ATR_BUFFER*signal["sweep_atr"]
    dist=entry-stop
    basis=signal["atr_entry_basis"]
    if dist<=0 or not (0.25*basis<=dist<=3.0*basis):
        return None
    target=entry+dist*rr
    last=min(entry_i+max_hold-1,len(bars)-1)
    if last<=entry_i:
        return None
    exit_i,exit_price,kind=None,None,None
    for i in range(entry_i,last+1):
        b=bars[i]
        if b[1]<=stop:
            exit_i,exit_price,kind=i,b[1],"GAP_STOP"
            break
        if b[3]<=stop:  # Both TP/SL touched: ALWAYS choose stop (conservative).
            exit_i,exit_price,kind=i,stop,"STOP"
            break
        if b[2]>=target:
            exit_i,exit_price,kind=i,target,"TARGET"
            break
    if exit_i is None:
        exit_i,exit_price,kind=last,bars[last][4],"TIME"
    entry_time=bars[entry_i][0]
    exit_time=bars[exit_i][0]+(HOUR if kind!="GAP_STOP" else 0)
    # Intrabar settlement order unknown; include only settlements before
    # the final hourly candle opens. This excludes ambiguous exit-bar cashflows.
    receipt_end=bars[exit_i][0]
    left=bisect.bisect_right(ftimes,entry_time)
    right=bisect.bisect_left(ftimes,receipt_end)
    receipt=-(prefix[right]-prefix[left])
    net_notional=(exit_price/entry-1)+receipt-2*(FEE_PER_SIDE+SLIPPAGE_PER_SIDE)
    stop_fraction=dist/entry
    exposure=min(0.95,0.005/stop_fraction)
    return {**signal,"entry_time":entry_time,"exit_time":exit_time,
            "entry_price":entry,"exit_price":exit_price,"stop":stop,"target":target,
            "exit_kind":kind,"funding_receipt":receipt,
            "net_notional":net_notional,"net":net_notional*exposure,
            "net_R":net_notional/stop_fraction,"exposure_fraction":exposure}


def summarize_trades(events):
    raw=len(events)
    selected=no_overlap(events)
    m=metrics([{"net":x["net"],"gross":x["net_notional"],"funding_receipt":x["funding_receipt"]}
               for x in selected])
    value=1.0
    peak=1.0
    maxdd=0.0
    for e in selected:
        value*=1+e["net"]
        peak=max(peak,value)
        maxdd=max(maxdd,1-value/peak)
    m["raw_signals"]=raw
    m["nonoverlap_trades"]=len(selected)
    m["ending_equity_multiple"]=round(value,6)
    m["closed_trade_max_dd_pct"]=round(maxdd*100,3)
    m["mean_net_R"]=round(sum(x["net_R"] for x in selected)/len(selected),4) if selected else None
    m["stop_count"]=sum(x["exit_kind"] in ("STOP","GAP_STOP") for x in selected)
    m["target_count"]=sum(x["exit_kind"]=="TARGET" for x in selected)
    return m


def backtest(data):
    bars,funds=data["klines"],data["funding"]
    ftimes=[r[0] for r in funds]
    prefix=[0.0]
    for t,r in funds:
        prefix.append(prefix[-1]+r)
    sig,scan=generate_causal_long_setups(bars,funds)
    groups=defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    rejected=0
    for candidate in sig:
        trade=simulate_long(candidate,bars,funds,ftimes,prefix)
        if trade is None:
            rejected+=1
            continue
        y=str(datetime.fromtimestamp(trade["entry_time"]/1000,timezone.utc).year)
        split="train" if trade["entry_time"]<SPLIT_MS else "later_historical"
        if split=="train" and trade["exit_time"]>=SPLIT_MS:
            continue
        keys=["all"]
        rate=trade["funding_rate_fraction"]
        if rate is None:
            pass
        elif rate>=0:
            keys.append("nonnegative")
        else:
            keys.append("negative")
            if trade["near_low"]:
                keys.append("negative_near_72h_low")
            if trade["near_confirmed_4h_proxy"]:
                keys.append("negative_confirmed_4h_proxy")
            if trade["near_low"] and trade["near_confirmed_4h_proxy"]:
                keys.append("negative_both")
        for grp in (y,split):
            for key in keys:
                groups[trade["phase"]][grp][key].append(trade)
    table={phase:{split:{key:summarize_trades(events) for key,events in grouped.items()}
                  for split,grouped in by_split.items()}
           for phase,by_split in groups.items()}
    return {"status":"RESEARCH_ONLY","method":"long-only SH-BMS-RTO hourly proxy 0.1",
            "observations":scan,"signals_total":len(sig),"risk_rejected":rejected,
            "fee_per_side":FEE_PER_SIDE,"slippage_per_side":SLIPPAGE_PER_SIDE,
            "take_profit_R":REWARD_R,"max_holding_hours":MAX_HOLD_BARS,
            "results":table,
            "caveats":["NOT exact Strong MTF SR v3.3, Eric or Pine v1.1",
                       "4h double pivot proxy confirmed only AFTER independent reactions",
                       "No original Eric, CVD or OI used; estimated data cannot be asserted equal",
                       "Hour-bar SL precedence pessimistic when both SL & TP touched",
                       "Funding is settled-cashflow approximation; ambiguous exit-bar settlement excluded",
                       "No account liquidation/intrabar equity drawdown simulated",
                       "Nested cohorts and historical 2025-26 cannot prove new statistically significant edge"]}


def markdown(r):
    lines=["# 五年BTC负资金费率 + SH/BMS/RTO独立交易模拟（仅多头代理）", "",
           f"扫描：{r['observations']}; 结构确认信号：{r['signals_total']}; 止损几何限制拒绝：{r['risk_rejected']}。", "",
           "规则：前20根下扫收回 → 5根内突破扫盘K最高价/先前3根高点 → 可选择5根内回踩收回；下一根小时K开盘成交。",
           "止损：扫盘最低价下0.2ATR；目标2R；48小时最多持有；同K止损先于止盈，双边费率+滑点0.16%，历史Funding近似。",
           "敞口≤95%权益；单笔预设风险预算0.5%权益，不能超出名义仓位上限。",
           "**重要：这不是用户原始Pine的逐K等价复刻；4H强区也是独立因果代理，2025—26并非未知未来数据。**", ""]
    for phase in PHASES:
        lines+=["## "+phase, "", "| 样本期 | 过滤条件 | 原始信号数 | 非重叠交易数 | 平均净权益收益% | PF | 结束净值倍数 | 收盘最大回撤% |",
                "|---|---|---:|---:|---:|---:|---:|---:|"]
        for period in ("train","later_historical"):
            for key in GROUPS:
                z=r["results"].get(phase,{}).get(period,{}).get(key)
                if z is None:
                    continue
                lines.append(f"| {period} | {key} | {z['raw_signals']} | {z['nonoverlap_trades']} | {z.get('mean_net_pct','—')} | {z.get('profit_factor','—')} | {z['ending_equity_multiple']} | {z['closed_trade_max_dd_pct']} |")
        lines.append("")
    lines+=["## 局限", *["- "+x for x in r["caveats"]], "",
            "不存在足够信号时，不得将0笔交易描述为过滤后的优异收益。"]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-dir",default="research/data/multiyear")
    p.add_argument("--output-dir",default="output/structure")
    args=p.parse_args()
    data,_=load_years(args.data_dir)
    r=backtest(data)
    folder=Path(args.output_dir)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"structure_funding.json").write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf-8")
    (folder/"structure_funding.md").write_text(markdown(r),encoding="utf-8")
    print(markdown(r))


if __name__=="__main__":
    main()
