"""Audit TradingView exported indicator CSV against a frozen Binance 1h chart.

This validator verifies timestamp / OHLC alignment, export columns and the
absence of obvious future-source timestamps. It DOES NOT claim that Python
proxy model matches Eric 1.9.10, SR 3.3, or Liquidity Sweep Pine bar-by-bar.
Per-algorithm exact signal parity requires an independent implementation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from engine.eric_core import d3_history

INTERVAL_HOUR_MS = 3_600_000
REQUIRED = {
    "sr": ("SR_1h_support_center","SR_1h_support_halfwidth",
           "SR_1h_resistance_center","SR_1h_source_close_unix_s",
           "SR_4h_support_center","SR_4h_support_halfwidth",
           "SR_4h_resistance_center","SR_4h_source_close_unix_s"),
    "eric": ("ERIC_1h_D3","ERIC_1h_STATE","ERIC_1h_PH...",
             "ERIC_4h_D3","ERIC_4h_STATE","ERIC_4h_PHASE",
             "ERIC_bull_divergence_confirmed","ERIC_reversal_oversold"),
    "sweep": ("SWEEP_sweep_long","SWEEP_bms_up","SWEEP_entry_long",
              "SWEEP_phase","SWEEP_bms_level","SWEEP_stop_line")
}
REQUIRED["eric"]=tuple("ERIC_1h_PHASE" if v=="ERIC_1h_PH..." else v for v in REQUIRED["eric"])


def numeric(raw):
    if raw is None:
        return None
    value=str(raw).strip()
    if value in ("","na","NA","NaN","null","None"):
        return None
    x=float(value.replace(",",""))
    if not math.isfinite(x):
        raise ValueError("Nonfinite export number: "+repr(value))
    return x


def time_ms(text, *, assume_utc=False):
    raw=str(text).strip()
    if not raw:
        raise ValueError("Empty timestamp")
    try:
        num=float(raw)
    except ValueError:
        num=None
    if num is not None:
        if not math.isfinite(num):
            raise ValueError("Nonfinite timestamp")
        return int(round(num * (1000 if abs(num)<10**11 else 1)))
    parsed=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if parsed.tzinfo is None:
        if not assume_utc:
            raise ValueError("Timezone-naive timestamps require --assume-utc")
        parsed=parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp()*1000)


def matching_column(headers, name):
    keys=[h for h in headers if name.casefold() in h.casefold()]
    if len(keys)!=1:
        raise ValueError(f"Expected one column containing {name!r}; got {keys}")
    return keys[0]


def load_csv(filepath, kind, *, assume_utc=False):
    with open(filepath,encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Missing CSV header")
        headers=reader.fieldnames
        # TradingView has historically used 'time' / 'Time'; avoid fuzzy ID columns.
        time_cols=[h for h in headers if h.strip().lower() in ("time","timestamp","datetime","date")]
        if len(time_cols)!=1:
            raise ValueError("Expected exactly one time column (Time/time/timestamp/date)")
        col={key:matching_column(headers,key) for key in REQUIRED[kind]}
        ohlc={}
        for name in ("open","high","low","close"):
            choices=[x for x in headers if x.strip().casefold()==name]
            if len(choices)!=1:
                raise ValueError("Expected unambiguous OHLC column "+name)
            ohlc[name]=choices[0]
        result=[]
        prev=-1
        for row in reader:
            t=time_ms(row[time_cols[0]],assume_utc=assume_utc)
            if t<=prev:
                raise ValueError("CSV time order/duplicate at "+str(t))
            prev=t
            bar={"open_time_ms":t}
            for key,c in ohlc.items():
                value=numeric(row[c])
                if value is None:
                    raise ValueError("Missing OHLC "+key)
                bar[key]=value
            bar["telemetry"]={name:numeric(row[c]) for name,c in col.items()}
            result.append(bar)
    if not result:
        raise ValueError("CSV contains no bars")
    return result


def compare_eric_d3(csv_bars, binance, *, tolerance=0.05, warmup_reference_bars=400,
                    minimum_comparison_bars=100):
    """Compare only 1H source mathematical D3, not the Eric episode/event engine."""
    reference=binance["klines"]
    candles=[{"low":row[3],"close":row[4]} for row in reference]
    computed=d3_history(candles)
    index={int(row[0]):i for i,row in enumerate(reference)}
    deviations=[]
    missing=0
    for row in csv_bars:
        idx=index.get(row["open_time_ms"])
        if idx is None or idx<warmup_reference_bars:
            continue
        reported=row["telemetry"].get("ERIC_1h_D3")
        expected=computed[idx]["d3"]
        if reported is None or expected is None:
            missing+=1
            continue
        deviations.append({"time_ms":row["open_time_ms"],
                           "python":expected,"tradingview":reported,
                           "error":abs(expected-reported)})
    if len(deviations)<minimum_comparison_bars:
        return {"status":"INSUFFICIENT_DATA","compared_bars":len(deviations),
                "missing_values_after_warmup":missing,
                "full_eric_algorithm_parity":"NOT_TESTED"}
    errors=sorted(x["error"] for x in deviations)
    bad=[x for x in deviations if x["error"]>tolerance]
    return {"status":"D3_MATH_MATCH" if not bad else "D3_MATH_MISMATCH",
            "compared_bars":len(deviations),
            "warmup_reference_bars":warmup_reference_bars,
            "tolerance_d3_points":tolerance,
            "max_abs_d3_difference":round(errors[-1],7),
            "p95_abs_d3_difference":round(errors[int(0.95*(len(errors)-1))],7),
            "mismatch_count":len(bad),
            "mismatch_examples":bad[:10],
            "missing_values_after_warmup":missing,
            "full_eric_algorithm_parity":"NOT_TESTED",
            "warning":"Only raw LC2/RSI/Stoch/K/D numerical math; no Episode or divergence/MTF state validation"}

def audit(csv_bars, binance, kind, *, tolerance=0.2, min_matches=100):
    if binance.get("symbol")!="BTCUSDT" or binance.get("market")!="USD-M_PERPETUAL":
        raise ValueError("Reference market mismatch: expected Binance BTCUSDT perpetual")
    bars=binance["klines"]
    index={int(x[0]):x for x in bars}
    verified=[]
    missing=0
    price_mismatch=[]
    source_future=[]
    plot_counts=defaultdict(int)
    event_counts=defaultdict(int)
    for row in csv_bars:
        b=index.get(row["open_time_ms"])
        if b is None:
            missing+=1
            continue
        verified.append(row)
        for name,col in (("open",1),("high",2),("low",3),("close",4)):
            delta=abs(row[name]-float(b[col]))
            if delta>tolerance:
                price_mismatch.append({"time":row["open_time_ms"],"field":name,
                                       "tradingview":row[name],"binance":b[col],
                                       "difference":round(delta,7)})
        for name,v in row["telemetry"].items():
            if v is None:
                continue
            plot_counts[name]+=1
            if ("_source_close_unix_s" in name and v*1000 >
                    row["open_time_ms"]+INTERVAL_HOUR_MS+1000):
                source_future.append({"time":row["open_time_ms"],"field":name,
                                      "source_close_unix_s":v})
            if name.startswith(("SWEEP_entry_","SWEEP_sweep_","ERIC_reversal_","ERIC_bull_divergence_")) and v>0.5:
                event_counts[name]+=1
    eric_math = compare_eric_d3(csv_bars, binance) if kind=="eric" else None
    if len(verified)<min_matches:
        raise ValueError(f"Only {len(verified)} time-matched bars, need {min_matches}; verify export symbol and range")
    result={
       "audit_version":"tradingview-export-audit-0.1",
       "kind":kind,
       "status":"CHART_DATA_VALIDATED" if not price_mismatch and not source_future else "CHART_DATA_MISMATCH",
       "pine_algorithm_parity":"NOT_TESTED",
       "eric_d3_core_comparison":eric_math,
       "tradingview_export_total_bars":len(csv_bars),
       "reference_bars":len(bars),
       "matched_bars":len(verified),
       "unmatched_tv_bars":missing,
       "first_match_utc":datetime.fromtimestamp(verified[0]["open_time_ms"]/1000,timezone.utc).isoformat(),
       "last_match_utc":datetime.fromtimestamp(verified[-1]["open_time_ms"]/1000,timezone.utc).isoformat(),
       "ohlc_tolerance_usdt":tolerance,
       "ohlc_mismatches":price_mismatch[:25],
       "ohlc_mismatch_total":len(price_mismatch),
       "future_source_time_violations":source_future[:25],
       "future_source_time_violation_total":len(source_future),
       "telemetry_non_null_counts":dict(plot_counts),
       "event_counts":dict(event_counts),
       "important_notes":[
          "Only source chart OHLC and source-close time checked, not full Pine-to-Python algorithm equality",
          "Original TradingView script must be compiled and CSV exported by user on BTCUSDT perpetual 1H",
          "Python 4H double-pivot support and sweep are proxies, not original indicator states",
          "Missing plots or mismatched OHLC invalidate cross-engine conclusions"
       ]
    }
    return result


def main():
    p=argparse.ArgumentParser(description="TradingView-Pine CSV vs Binance reference")
    p.add_argument("--csv",required=True)
    p.add_argument("--kind",required=True,choices=sorted(REQUIRED))
    p.add_argument("--reference",default="research/data/multiyear/btcusdt_2026_through_2026-11-20.json")
    p.add_argument("--assume-utc",action="store_true",help="Interpret timezone-naive ISO times as UTC")
    p.add_argument("--min-matches",type=int,default=100)
    p.add_argument("--ohlc-tolerance-usdt",type=float,default=0.2)
    p.add_argument("--output",default="output/parity_audit.json")
    args=p.parse_args()
    rows=load_csv(args.csv,args.kind,assume_utc=args.assume_utc)
    reference=json.loads(Path(args.reference).read_text(encoding="utf-8"))
    result=audit(rows,reference,args.kind,min_matches=args.min_matches,
                 tolerance=args.ohlc_tolerance_usdt)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if result["status"]!="CHART_DATA_VALIDATED":
        raise SystemExit(2)


if __name__=="__main__":
    main()
