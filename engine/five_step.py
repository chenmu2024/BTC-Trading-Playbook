"""Research-only causal price-action observations for a PURE five-step funnel.

No Eric signals, no Strong SR v3.3 parity, no order placement. Every reported
SH, BMS and RTO event uses only bars whose close is already known. Statuses
are descriptive, and none constitutes a validated or profitable trade signal.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

STAGES = ("WAIT_BMS", "EXPIRED_BMS", "INVALIDATED_BEFORE_BMS",
          "WAIT_RTO", "EXPIRED_RTO", "INVALIDATED_BEFORE_RTO",
          "CONFIRMED_RTO")


def _utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def atr_history(candles: list[dict], period: int = 14) -> list[float | None]:
    """Wilder ATR with initial SMA seed; no forward-looking bar."""
    if period < 2:
        raise ValueError("ATR period must be >=2")
    result: list[float | None] = []
    value: float | None = None
    for i, bar in enumerate(candles):
        prev = candles[i - 1]["close"] if i else bar["close"]
        tr = max(bar["high"]-bar["low"], abs(bar["high"]-prev), abs(bar["low"]-prev))
        if not math.isfinite(tr) or tr < 0:
            raise ValueError("Invalid ATR source")
        if i == period - 1:
            value = sum(
                max(candles[k]["high"] - candles[k]["low"],
                    abs(candles[k]["high"]-(candles[k-1]["close"] if k else candles[k]["close"])),
                    abs(candles[k]["low"]-(candles[k-1]["close"] if k else candles[k]["close"])))
                for k in range(period)
            ) / period
        elif i >= period:
            assert value is not None
            value = (value * (period - 1) + tr) / period
        result.append(value)
    return result


def _validate(candles: list[dict], *, expected_hour_ms: int = 3_600_000) -> None:
    previous = -1
    for c in candles:
        opened, closed = int(c["open_time_ms"]), int(c["close_time_ms"])
        if opened <= previous or (previous >= 0 and opened-previous != expected_hour_ms):
            raise ValueError("1h candles must be ordered and contiguous")
        if closed < opened or closed >= opened+expected_hour_ms:
            raise ValueError("Invalid 1h close timestamp")
        if not all(math.isfinite(float(c[k])) for k in ("open", "high", "low", "close", "volume")):
            raise ValueError("Nonfinite price data")
        if (c["low"] > min(c["open"],c["close"])
                or c["high"] < max(c["open"],c["close"]) or c["volume"] < 0):
            raise ValueError("Invalid OHLCV bar")
        previous = opened


def observe_funnel(candles: list[dict], settings: dict | None = None,
                   *, recent_bars: int = 72, max_display: int = 8) -> dict:
    """Descriptive SH/BMS/RTO with per-candidate invalidation and strict windows.

    Each observed bar is immutable. An earlier SH cannot be confirmed by BMS
    or RTO after its window. Sweep candle itself cannot also be the BMS.
    If intrabar order is unknowable and price touches invalidation and breakout
    on the same 1h bar, invalidation wins.
    """
    s = settings or {}
    lb = int(s.get("lookback_bars", 20))
    vol_bars = int(s.get("average_volume_bars", 20))
    confirm = int(s.get("confirm_bars", 4))
    retest = int(s.get("retest_bars", 5))
    micro = int(s.get("microstructure_lookback_bars", 3))
    atr_period = int(s.get("atr_period", 14))
    min_ratio = float(s.get("minimum_sweep_volume_ratio", .8))
    min_wick = float(s.get("minimum_sweep_wick_fraction", .30))
    penetration = float(s.get("minimum_sweep_penetration_atr", .10))
    reclaim = float(s.get("minimum_sweep_reclaim_atr", .05))
    min_body = float(s.get("minimum_bms_body_atr", .20))
    tol_above = float(s.get("retest_touch_atr_above", .15))
    tol_below = float(s.get("retest_touch_atr_below", .35))
    if not (lb >= 4 and vol_bars >= 4 and micro >= 2 and confirm >= 1
            and retest >= 1 and recent_bars >= 1 and max_display >= 1
            and min_ratio > 0 and 0 <= min_wick < 1 and penetration >= 0
            and reclaim >= 0 and min_body >= 0 and tol_above >= 0 and tol_below >= 0):
        raise ValueError("Invalid pure five-step research configuration")
    _validate(candles)
    atr = atr_history(candles, atr_period)
    start = max(lb, vol_bars, micro, atr_period-1)
    if len(candles) <= start:
        return {"status":"DATA_INSUFFICIENT", "total_candidates":0,
                "latest_by_side":{"LONG":None, "SHORT":None},
                "events":[], "method":"closed-1h-price-action-proxy-v0.1",
                "not_a_trade_signal":True}
    first = max(start, len(candles)-max(recent_bars, confirm + retest + 2))
    events: list[dict] = []
    for i in range(first, len(candles)):
        bar = candles[i]
        a = atr[i]
        if a is None or a <= 0:
            continue
        past = candles[i-lb:i]
        previous_low = min(c["low"] for c in past)
        previous_high = max(c["high"] for c in past)
        avg_volume = sum(c["volume"] for c in candles[i-vol_bars:i])/vol_bars
        if not avg_volume or bar["volume"] < avg_volume*min_ratio:
            continue
        spread = bar["high"]-bar["low"]
        if spread <= 0:
            continue
        for side in (1,-1):
            wick = ((min(bar["open"],bar["close"])-bar["low"])/spread if side == 1
                    else (bar["high"]-max(bar["open"],bar["close"]))/spread)
            swept = (bar["low"] < previous_low-penetration*a and
                     bar["close"] > previous_low+reclaim*a if side == 1 else
                     bar["high"] > previous_high+penetration*a and
                     bar["close"] < previous_high-reclaim*a)
            if not swept or wick < min_wick:
                continue
            reference = previous_low if side == 1 else previous_high
            extreme = bar["low"] if side == 1 else bar["high"]
            if side == 1:
                bms_level = max(bar["high"], *(x["high"] for x in candles[i-micro:i]))
            else:
                bms_level = min(bar["low"], *(x["low"] for x in candles[i-micro:i]))
            last = len(candles)-1
            event = dict(direction="LONG" if side == 1 else "SHORT",
                         status="WAIT_BMS", sweep_index=i,
                         sweep_close_utc=_utc(int(bar["close_time_ms"])+1),
                         reference=reference, sweep_extreme=extreme,
                         sweep_volume_multiple=round(bar["volume"]/avg_volume,3),
                         wick_fraction=round(wick,4), bms_level=bms_level,
                         bms_close_utc=None, rto_close_utc=None,
                         bms_deadline_utc=_utc(int(candles[i]["close_time_ms"])+1+confirm*3_600_000),
                         invalidation_reason=None,
                         is_recent_confirmation=False)
            bms_index = None
            for j in range(i+1,min(last,i+confirm)+1):
                c = candles[j]
                invalid = c["low"] <= extreme if side == 1 else c["high"] >= extreme
                if invalid:
                    event["status"]="INVALIDATED_BEFORE_BMS"
                    event["invalidation_reason"]="Sweep extreme broken before BMS"
                    break
                body = (c["close"]-c["open"])*side
                breakout = (c["close"] > bms_level if side == 1 else c["close"] < bms_level)
                if breakout and body >= min_body*(atr[j] or a):
                    bms_index=j
                    event["status"]="WAIT_RTO"
                    event["bms_close_utc"]=_utc(int(c["close_time_ms"])+1)
                    event["bms_index"]=j
                    event["rto_deadline_utc"]=_utc(int(c["close_time_ms"])+1+retest*3_600_000)
                    break
            if event["status"]=="WAIT_BMS" and last >= i+confirm:
                event["status"]="EXPIRED_BMS"
            if bms_index is not None:
                for k in range(bms_index+1,min(last,bms_index+retest)+1):
                    c=candles[k]
                    invalid = c["low"]<=extreme if side == 1 else c["high"]>=extreme
                    if invalid:
                        event["status"]="INVALIDATED_BEFORE_RTO"
                        event["invalidation_reason"]="Sweep extreme broken before RTO"
                        break
                    ak=atr[k] or a
                    if side==1:
                        touch=(c["low"] <= bms_level+tol_above*ak and
                               c["low"] >= bms_level-tol_below*ak)
                        reclaimed=c["close"]>bms_level and c["close"]>c["open"]
                    else:
                        touch=(c["high"]>=bms_level-tol_above*ak and
                               c["high"]<=bms_level+tol_below*ak)
                        reclaimed=c["close"]<bms_level and c["close"]<c["open"]
                    if touch and reclaimed:
                        event["status"]="CONFIRMED_RTO"
                        event["rto_close_utc"]=_utc(int(c["close_time_ms"])+1)
                        event["rto_index"]=k
                        event["is_recent_confirmation"]=k==last
                        break
                if event["status"]=="WAIT_RTO" and last>=bms_index+retest:
                    event["status"]="EXPIRED_RTO"
            events.append(event)
    events.sort(key=lambda x:x["sweep_index"],reverse=True)
    latest={side:next((e for e in events if e["direction"]==side),None)
            for side in ("LONG","SHORT")}
    summary={stage:sum(e["status"]==stage for e in events) for stage in STAGES}
    return {"status":"PRICE_ACTION_PROXY","method":"closed-1h-price-action-proxy-v0.1",
            "not_a_trade_signal":True,
            "unverified_original_pine_parity":True,
            "bms_confirm_window_bars":confirm,"rto_window_bars":retest,
            "config_volume_min_ratio":min_ratio,
            "total_candidates":len(events),
            "stage_counts":summary,
            "latest_by_side":latest,
            "events":events[:max_display],
            "warning":"No v1.1/Pine parity; RTO candidate != validated execution signal."}
