"""Research classification of settled BTCUSDT funding: no automatic trade signals."""
from __future__ import annotations

import math
from datetime import datetime, timezone

HOUR = 3_600_000
DAY = 86_400_000


def funding_regime(history: list | None, as_of_ms: int, *, lookback_days: int = 90,
                   min_samples: int = 60, extreme_percentile: float = 0.10,
                   streak_required: int = 3) -> dict:
    """Negative funding is a contrarian *watch*, never a confirmed bottom.

    Use only settled records observable as of the snapshot. Normalize each
    rate linearly to an equivalent 8h rate using the preceding settlement
    interval, because Binance settlement frequency can vary.
    """
    unknown = {"status": "UNKNOWN", "regime": "UNKNOWN", "long_entry_signal": False}
    if not isinstance(history, list) or len(history) < 2:
        return {**unknown, "reason": "Insufficient settled funding history"}
    try:
        rows = sorted((int(x["fundingTime"]), float(x["fundingRate"]))
                      for x in history if 0 <= int(x["fundingTime"]) <= as_of_ms)
    except (TypeError, ValueError, KeyError):
        return {**unknown, "reason": "Malformed funding history"}
    rows = [(ts, rate) for ts, rate in rows if ts >= as_of_ms - lookback_days * DAY]
    if len(rows) < 2 or len({ts for ts, _ in rows}) != len(rows):
        return {**unknown, "reason": "Too few or duplicate settlements"}
    if any(not math.isfinite(rate) or abs(rate) >= 1 for _, rate in rows):
        return {**unknown, "reason": "Nonfinite or invalid funding"}
    normalized = []
    for (previous, _), (ts, raw) in zip(rows, rows[1:]):
        interval_h = (ts - previous) / HOUR
        if 0.5 <= interval_h <= 8.1:
            normalized.append((ts, raw, interval_h, raw * 8.0 / interval_h))
    if not normalized or normalized[-1][0] != rows[-1][0]:
        return {**unknown, "reason": "Latest settlement interval unavailable"}
    ts, rate, interval, equivalent = normalized[-1]
    if as_of_ms - ts > (2.5 * interval + 0.25) * HOUR:
        return {**unknown, "status": "STALE", "reason": "Last settlement is stale",
                "last_funding_time_utc": datetime.fromtimestamp(ts/1000, timezone.utc).isoformat()}
    streak = 0
    for _, raw, _, _ in reversed(normalized):
        if raw >= 0:
            break
        streak += 1
    rank = (sum(r[3] <= equivalent for r in normalized) / len(normalized)
            if len(normalized) >= min_samples else None)
    seven = [r[1] for r in normalized if r[0] >= as_of_ms - 7 * DAY]
    negative = rate < 0
    if not negative:
        regime = "NON_NEGATIVE"
    elif streak >= streak_required and rank is not None and rank <= extreme_percentile:
        regime = "DEEP_NEGATIVE_WATCH"
    elif streak >= streak_required:
        regime = "PERSISTENT_NEGATIVE_WATCH"
    else:
        regime = "NEGATIVE_WATCH"
    return {
        "status": "AVAILABLE", "regime": regime, "long_entry_signal": False,
        "last_rate_fraction": rate, "last_rate_percent": round(rate*100, 8),
        "last_8h_equivalent_percent": round(equivalent*100, 8),
        "settlement_interval_hours": interval,
        "last_funding_time_utc": datetime.fromtimestamp(ts/1000, timezone.utc).isoformat(),
        "sample_count": len(normalized),
        "sample_start_utc": datetime.fromtimestamp(normalized[0][0]/1000, timezone.utc).isoformat(),
        "negative_streak": streak,
        "negative_share_last_7d": sum(x < 0 for x in seven)/len(seven) if seven else None,
        "percentile_rank": rank,
        "turning_less_negative": negative and len(normalized) > 1 and equivalent > normalized[-2][3],
        "interpretation": "Negative funding can flag potential crowded shorts, but can persist in downtrends; price confirmation required.",
        "disclaimer": "Observed history only, linear interval normalization, not predictive buy probability.",
    }
