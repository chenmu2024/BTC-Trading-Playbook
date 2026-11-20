"""No-lookahead Binance USD-M BTCUSDT snapshot and conservative analysis.

This engine deliberately DOES NOT implement Eric v1.9.10 or Strong MTF SR v3.3.
Its levels and sweep observations are explicitly labelled PROXIES, not Pine signals.
No authenticated APIs, trading calls, order submission, or secrets.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://fapi.binance.com"
FUTURES_DATA = "https://fapi.binance.com"
INTERVALS = ("1w", "1d", "4h", "1h", "30m")


def utc_ms() -> int:
    return int(time.time() * 1000)


def iso_ms(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


def get_json(path: str, params: dict, base: str = BASE, timeout: int = 15):
    url = base.rstrip("/") + path + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "BTC-Trading-Playbook/0.2 research; public-api", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Public data request failed: {path}: {type(exc).__name__}: {exc}") from exc
    if isinstance(data, dict) and "code" in data and "msg" in data:
        raise RuntimeError(f"Binance data error on {path}: {data['code']}: {data['msg']}")
    return data


def parse_klines(rows: list, now_ms: int) -> list[dict]:
    """Ignore any unsettled bar; enforce chronological, unique close times."""
    result = []
    previous_open = -1
    for r in rows:
        if len(r) < 11:
            raise ValueError("Incomplete Binance kline (expected at least 11 fields)")
        opened, closed = int(r[0]), int(r[6])
        if opened <= previous_open or closed < opened:
            raise ValueError("Klines out of chronological order or duplicated")
        previous_open = opened
        if closed >= now_ms:
            continue
        candle = dict(open_time_ms=opened, close_time_ms=closed,
                      open=float(r[1]), high=float(r[2]), low=float(r[3]),
                      close=float(r[4]), volume=float(r[5]),
                      taker_buy_base=float(r[9]))
        if (not all(math.isfinite(candle[x]) for x in ("open", "high", "low", "close", "volume", "taker_buy_base"))
                or candle["high"] < candle["low"] or candle["volume"] < 0
                or not (candle["low"] <= candle["open"] <= candle["high"])
                or not (candle["low"] <= candle["close"] <= candle["high"])
                or candle["taker_buy_base"] < 0 or candle["taker_buy_base"] > candle["volume"] + 1e-6):
            raise ValueError("Invalid OHLCV/taker buy values in market response")
        result.append(candle)
    return result


def fetch_snapshot(symbol: str = "BTCUSDT", now_ms: int | None = None) -> dict:
    """Read-only Binance USD-M endpoints. Partial OI/funding failures are explicit."""
    now = utc_ms() if now_ms is None else now_ms
    if symbol != "BTCUSDT":
        raise ValueError("Research profile currently restricted to BTCUSDT")
    snapshot = dict(exchange="Binance", market="USD-M_PERPETUAL", symbol=symbol,
                    fetched_at_utc=iso_ms(now), source_base=BASE,
                    klines={}, oi=None, funding=None, errors={})
    for interval in INTERVALS:
        try:
            rows = get_json("/fapi/v1/klines", dict(symbol=symbol, interval=interval, limit=260))
            snapshot["klines"][interval] = parse_klines(rows, now)
        except (RuntimeError, ValueError) as exc:
            snapshot["errors"][f"klines_{interval}"] = str(exc)
    try:
        hist = get_json("/futures/data/openInterestHist", dict(symbol=symbol, period="1h", limit=24), base=FUTURES_DATA)
        if not isinstance(hist, list) or not hist:
            raise ValueError("OI history empty")
        eligible = [x for x in hist if int(x["timestamp"]) <= now]
        snapshot["oi"] = eligible[-2:] if eligible else None
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        snapshot["errors"]["oi"] = str(exc)
    try:
        rates = get_json("/fapi/v1/fundingRate", dict(symbol=symbol, limit=3))
        if not isinstance(rates, list):
            raise ValueError("Funding history invalid")
        eligible = [x for x in rates if int(x["fundingTime"]) <= now]
        snapshot["funding"] = eligible[-1] if eligible else None
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        snapshot["errors"]["funding"] = str(exc)
    return snapshot


def ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period or period < 2:
        return None
    value = sum(closes[:period]) / period
    factor = 2.0 / (period + 1.0)
    for price in closes[period:]:
        value = price * factor + value * (1.0 - factor)
    return value


def trend(candles: list[dict], fast: int = 50, slow: int = 200) -> dict:
    if not candles or len(candles) < slow:
        return dict(status="DATA_INSUFFICIENT", count=len(candles), fast_ema=None, slow_ema=None)
    latest = candles[-1]
    closes = [b["close"] for b in candles]
    a, b = ema(closes, fast), ema(closes, slow)
    label = "BULL" if latest["close"] > a > b else "BEAR" if latest["close"] < a < b else "NEUTRAL"
    return dict(status=label, close=latest["close"], fast_ema=round(a, 3), slow_ema=round(b, 3),
                last_closed_bar_utc=iso_ms(latest["close_time_ms"] + 1), count=len(candles),
                method=f"EMA{fast}/{slow} proxy; closed bars only")


def levels(candles: list[dict], window: int = 20) -> dict:
    """Prior completed candles EXCLUDING the current last completed bar."""
    if len(candles) < window + 1:
        return dict(status="DATA_INSUFFICIENT")
    previous = candles[-(window + 1):-1]
    return dict(status="PROXY_ONLY", lookback=window,
                prior_high=max(c["high"] for c in previous),
                prior_low=min(c["low"] for c in previous),
                latest_close=candles[-1]["close"],
                as_of_utc=iso_ms(candles[-1]["close_time_ms"] + 1),
                label="Prior-bar extrema proxy, NOT Strong MTF SR v3.3")


def sweep_candidates(candles: list[dict], lookback: int = 20, confirm_bars: int = 4,
                     minimum_volume_ratio: float = 0.8) -> list[dict]:
    """Describe recent sweep/close-back candidates only, never assert BMS/RTO parity."""
    if len(candles) < lookback + 21:
        return []
    found = []
    start = max(lookback + 20, len(candles) - confirm_bars - 1)
    for i in range(start, len(candles)):
        bar = candles[i]
        previous = candles[i-lookback:i]
        prior_high = max(c["high"] for c in previous)
        prior_low = min(c["low"] for c in previous)
        avgvol = sum(c["volume"] for c in candles[i-20:i]) / 20
        if avgvol <= 0 or bar["volume"] < avgvol * minimum_volume_ratio:
            continue
        side = ("LONG" if bar["low"] < prior_low and bar["close"] > prior_low else
                "SHORT" if bar["high"] > prior_high and bar["close"] < prior_high else None)
        if side is None:
            continue
        after = candles[i+1:]
        invalid = (any(c["low"] <= bar["low"] for c in after) if side == "LONG"
                   else any(c["high"] >= bar["high"] for c in after))
        micro = (max(c["high"] for c in candles[i-3:i]) if side == "LONG"
                 else min(c["low"] for c in candles[i-3:i]))
        break_proxy = (any(c["close"] > micro for c in after) if side == "LONG"
                       else any(c["close"] < micro for c in after))
        stage = ("INVALID" if invalid else "BMS_PROXY_NOT_RTO_VERIFIED" if break_proxy
                 else "SWEEP_CANDIDATE_WAIT_BMS")
        found.append(dict(direction=side, stage=stage,
                          sweep_bar_utc=iso_ms(bar["close_time_ms"] + 1),
                          swept_reference=prior_low if side == "LONG" else prior_high,
                          sweep_extreme=bar["low"] if side == "LONG" else bar["high"],
                          microstructure_proxy=micro,
                          confirmation="Proxy only; not TradingView V1.1/SH+BMS+RTO parity"))
    return found


def delta_summary(candles: list[dict]) -> dict:
    """Binance 1h kline taker delta (base BTC); not tick-accurate CVD."""
    if len(candles) < 24:
        return dict(status="DATA_INSUFFICIENT")
    last = candles[-24:]
    bybar = [2 * b["taker_buy_base"] - b["volume"] for b in last]
    return dict(status="BINANCE_KLINE_BASE_VOLUME",
                last_1h_delta_btc=round(bybar[-1], 5),
                last_24h_net_delta_btc=round(sum(bybar), 5),
                window_start_utc=iso_ms(last[0]["open_time_ms"]),
                window_end_utc=iso_ms(last[-1]["close_time_ms"] + 1),
                meaning="Taker buys minus taker sells in base BTC; not ExoCharts CVD")


def derivatives(snapshot: dict) -> dict:
    result = dict(oi=dict(status="UNKNOWN"), funding=dict(status="UNKNOWN"))
    history = snapshot.get("oi")
    if isinstance(history, list) and len(history) >= 2:
        try:
            old, new = history[-2:]
            a, b = float(old["sumOpenInterest"]), float(new["sumOpenInterest"])
            if a > 0 and b >= 0:
                result["oi"] = dict(status="AVAILABLE", unit="BTC contracts, exchange reported",
                                    latest=b, change_pct=round(100*(b/a-1), 4),
                                    as_of_utc=iso_ms(int(new["timestamp"])),
                                    inference="OI cannot identify net long vs short initiator")
        except (ValueError, TypeError, KeyError):
            pass
    raw = snapshot.get("funding")
    if isinstance(raw, dict):
        try:
            result["funding"] = dict(status="AVAILABLE", rate_fraction=float(raw["fundingRate"]),
                                     as_of_utc=iso_ms(int(raw["fundingTime"])),
                                     meaning="Latest completed funding settlement, not live predicted rate")
        except (ValueError, TypeError, KeyError):
            pass
    return result


def analyze(snapshot: dict, config: dict, repo_commit: str = "unknown") -> dict:
    frames = snapshot.get("klines", {})
    fast = int(config["trend"]["ema_fast"])
    slow = int(config["trend"]["ema_slow"])
    lkb = int(config["liquidity"]["lookback_bars"])
    cbars = int(config["liquidity"]["confirm_bars"])
    vol = float(config["liquidity"]["minimum_sweep_volume_ratio"])
    summaries = {tf: trend(frames.get(tf, []), fast, slow) for tf in INTERVALS}
    areas = {tf: levels(frames.get(tf, []), lkb) for tf in ("1d", "4h", "1h")}
    candidates = sweep_candidates(frames.get("1h", []), lkb, cbars, vol)
    delta = delta_summary(frames.get("1h", []))
    derivatives_result = derivatives(snapshot)
    mandatory = ("1d", "4h", "1h")
    complete = all(summaries[tf]["status"] != "DATA_INSUFFICIENT" for tf in mandatory)
    if not complete:
        state = "DATA_INSUFFICIENT"
    else:
        state = "WAIT"  # External Pine parity and RTO validation not yet established.
    bias = ("BEAR" if summaries["1d"]["status"] == summaries["4h"]["status"] == "BEAR"
            else "BULL" if summaries["1d"]["status"] == summaries["4h"]["status"] == "BULL"
            else "MIXED_OR_NEUTRAL")
    return dict(engine="public-data-proxy-0.2", repo_commit=repo_commit,
                exchange=snapshot.get("exchange"), market=snapshot.get("market"),
                symbol=snapshot.get("symbol"), fetched_at_utc=snapshot.get("fetched_at_utc"),
                data_errors=snapshot.get("errors", {}), decision=state, directional_context=bias,
                trends=summaries, areas=areas, sweep_observations=candidates,
                candle_taker_delta=delta, derivatives=derivatives_result,
                pine_parity={"strong_support_resistance_v3_3":"UNKNOWN",
                             "eric_swing_v1_9_10":"UNKNOWN",
                             "liquidity_sweep_v1_1":"UNKNOWN"},
                risk=dict(trend_trade_max_fraction=config["risk"]["trend_trade_max_equity_fraction"],
                          countertrend_max_fraction=config["risk"]["countertrend_max_equity_fraction"]),
                caution="Research-only; no validated trade entry, backtest parity or auto execution")


def markdown_report(r: dict) -> str:
    lines = [f"# BTCUSDT 交易观察 | {r.get('fetched_at_utc', 'unknown')}",
             "", f"- 仓库提交：{r['repo_commit']}",
             f"- 市场：{r['exchange']} {r['market']} {r['symbol']}",
             f"- 决策：**{r['decision']}**；高周期环境：**{r['directional_context']}**",
             "- 交易信号：目前只支持基础代理计算；Eric/强支撑压力/完整SH+BMS+RTO均未验证一致性。",
             "", "## 已收盘K线趋势代理"]
    for tf in ("1w", "1d", "4h", "1h", "30m"):
        d = r["trends"][tf]
        lines.append(f"- {tf}: {d['status']}; close={d.get('close', 'unknown')}, EMA50={d.get('fast_ema', 'unknown')}, EMA200={d.get('slow_ema', 'unknown')}; 最新完整K结束={d.get('last_closed_bar_utc', 'unknown')}")
    lines.append("\n## 结构位置（非 v3.3 官方值）")
    for tf in ("1d", "4h", "1h"):
        a = r["areas"][tf]
        lines.append(f"- {tf}: {a.get('status')}, 前{a.get('lookback','?')}根已收盘K高点={a.get('prior_high','?')}，低点={a.get('prior_low','?')}")
    lines += ["", "## 近期1小时扫盘候选（非原Pine信号）"]
    if r["sweep_observations"]:
        for x in r["sweep_observations"]:
            lines.append(f"- {x['direction']}: {x['stage']}, 扫盘K结束={x['sweep_bar_utc']}, 参考={x['swept_reference']}, 极值={x['sweep_extreme']}")
    else:
        lines.append("- 当前窗口无符合代理定义的扫盘候选。")
    d = r["candle_taker_delta"]
    lines += ["", "## 成交与衍生品",
              f"- K线主动成交量差：{d.get('status')}, 最近1H={d.get('last_1h_delta_btc','?')} BTC，24H净值={d.get('last_24h_net_delta_btc','?')} BTC（不是逐笔CVD）。"]
    for key in ("oi", "funding"):
        lines.append(f"- {key.upper()}: {json.dumps(r['derivatives'][key], ensure_ascii=False)}")
    if r["data_errors"]:
        lines += ["", "## 数据获取异常"]
        for key, val in r["data_errors"].items():
            lines.append(f"- {key}: {val}")
    lines += ["", "## 条件分析与失效",
              "- 多头候选：已知支撑区域的下扫收回 → 后续结构确认 → RTO确认；任何一步缺失均等待。",
              "- 空头候选：已知压力区域的上扫收回 → 后续结构确认 → RTO确认；任何一步缺失均等待。",
              "- 强区、Eric与V1.1原指标值目前未复现；不可依据这里的代理水平生成精确实盘入场、止损或止盈价。",
              "- 风险研究上限：顺势0.5%权益、逆势0.25%权益；不是下单建议。",
              "", "> 报告仅为定时点条件观察，不会后台运行或自动下单。"]
    return "\n".join(lines) + "\n"
