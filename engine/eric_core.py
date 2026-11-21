"""Source-faithful Eric v1.9.10 BASE D3 math, without Episode or alerts.

Based directly on pine/eric_swing_filter_v1_9_10.pine lines 323-357:
    src=(low+close)/2, Wilder RSI(20), Stoch RSI(26) shifted -50,
    SMA K(4), SMA D(3), stoch-valid continuity gate 4+3-1.
This implementation has NOT been checked against actual TradingView exports.
Finite input history makes Wilder's RMA seed differ from full-chart history.
It is NEVER an Eric state/divergence/entry or original indicator parity claim.
"""
from __future__ import annotations

import math
from collections import deque


def d3_history(candles: list[dict], *, rsi_len: int = 20, stoch_len: int = 26,
               k_len: int = 4, d_len: int = 3) -> list[dict]:
    if min(rsi_len, stoch_len, k_len, d_len) < 1 or rsi_len < 2:
        raise ValueError("All smoothing periods must be valid, RSI >= 2")
    if not candles:
        return []

    src=[]
    for candle in candles:
        low=float(candle["low"])
        close=float(candle["close"])
        if not (math.isfinite(low) and math.isfinite(close) and low<=close):
            raise ValueError("Bad source input for Eric base D3")
        src.append((low+close)/2)

    gain_window=deque(maxlen=rsi_len)
    loss_window=deque(maxlen=rsi_len)
    avg_gain=None
    avg_loss=None
    rsi_series=[]
    prev=None
    for value in src:
        if prev is None:
            rsi_series.append(None)
        else:
            diff=value-prev
            gain=max(diff,0.0)
            loss=max(-diff,0.0)
            if avg_gain is None:
                gain_window.append(gain)
                loss_window.append(loss)
                if len(gain_window)==rsi_len:
                    avg_gain=sum(gain_window)/rsi_len
                    avg_loss=sum(loss_window)/rsi_len
            else:
                avg_gain=(avg_gain*(rsi_len-1)+gain)/rsi_len
                avg_loss=(avg_loss*(rsi_len-1)+loss)/rsi_len
            if avg_gain is None or avg_loss is None:
                rsi_series.append(None)
            elif avg_loss==0:
                rsi_series.append(100.0)
            elif avg_gain==0:
                rsi_series.append(0.0)
            else:
                rsi_series.append(100.0-100.0/(1+avg_gain/avg_loss))
        prev=value

    k_values=deque(maxlen=k_len)
    d_values=deque(maxlen=d_len)
    valid_stoch_bars=0
    result=[]
    for idx,rsi in enumerate(rsi_series):
        local=[x for x in rsi_series[max(0,idx-stoch_len+1):idx+1] if x is not None]
        valid=rsi is not None and bool(local) and max(local)>min(local)
        if valid:
            centered=(rsi-min(local))/(max(local)-min(local))*100.0-50.0
            valid_stoch_bars+=1
            k_values.append(centered)
            k=sum(k_values)/k_len if len(k_values)==k_len else None
            if k is not None:
                d_values.append(k)
            d=sum(d_values)/d_len if len(d_values)==d_len else None
        else:
            valid_stoch_bars=0
            d=None
            # ta.sma() skips na, so retain existing SMA input windows.
            # The continuity gate below prevents stale values being used.
        core_ready=valid and valid_stoch_bars>=k_len+d_len-1 and d is not None
        result.append({"rsi":rsi,
                       "d3":d if core_ready else None,
                       "stoch_valid":valid,
                       "continuous_stoch_bars":valid_stoch_bars,
                       "core_ready":core_ready})
    return result


def latest_d3(candles: list[dict]) -> dict:
    values=d3_history(candles)
    if not values:
        return {"status":"DATA_INSUFFICIENT"}
    last=values[-1]
    if not last["core_ready"]:
        return {"status":"CORE_NOT_READY",
                "continuous_stoch_bars":last["continuous_stoch_bars"]}
    d3=last["d3"]
    return {
      "status":"CORE_FORMULA_PORT_UNVERIFIED",
      "d3":round(d3,6),
      "rsi":round(last["rsi"],6),
      "relative_extreme":"OVERBOUGHT_SIDE" if d3>=40 else "OVERSOLD_SIDE" if d3<=-40 else "NEUTRAL_CORE_RANGE",
      "core_ready":True,
      "verified_against_pine_csv":False,
      "not_computed":["Episode state","ordinary/stable/reversal events",
                      "strict divergence","MTF resonance","Eric v1.9.10 final signals"],
      "warmup_caveat":"Finite 260-bar RMA seed; may differ from full TradingView chart"
    }
