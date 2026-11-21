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
from .funding import funding_regime
from .eric_core import latest_d3
from .five_step import observe_funnel

BASE = "https://fapi.binance.com"
FUTURES_DATA = "https://fapi.binance.com"
INTERVALS = ("1w", "1d", "4h", "1h", "30m")
INTERVAL_MS = {"1w": 604800000, "1d": 86400000, "4h": 14400000, "1h": 3600000, "30m": 1800000}


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


def parse_klines(rows: list, now_ms: int, expected_interval_ms: int | None = None) -> list[dict]:
    """Ignore any unsettled bar; enforce chronological, unique close times."""
    result = []
    previous_open = -1
    for r in rows:
        if len(r) < 11:
            raise ValueError("Incomplete Binance kline (expected at least 11 fields)")
        opened, closed = int(r[0]), int(r[6])
        if opened <= previous_open or closed < opened:
            raise ValueError("Klines out of chronological order or duplicated")
        if expected_interval_ms is not None and previous_open >= 0 and opened - previous_open != expected_interval_ms:
            raise ValueError("Missing Kline interval or unexpected spacing")
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
                    klines={}, oi=None, funding=None, funding_history=None, errors={})
    for interval in INTERVALS:
        try:
            rows = get_json("/fapi/v1/klines", dict(symbol=symbol, interval=interval, limit=260))
            closed = parse_klines(rows, now, expected_interval_ms=INTERVAL_MS[interval])
            if not closed or now - closed[-1]["close_time_ms"] > 2 * INTERVAL_MS[interval] + 1000:
                raise ValueError("Missing or stale most recent closed Kline")
            snapshot["klines"][interval] = closed
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
        rates = get_json("/fapi/v1/fundingRate", dict(symbol=symbol, limit=1000))
        if not isinstance(rates, list):
            raise ValueError("Funding history invalid")
        eligible = [x for x in rates if int(x["fundingTime"]) <= now]
        snapshot["funding_history"] = eligible
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
    five_step = observe_funnel(frames.get("1h", []), config["liquidity"])
    delta = delta_summary(frames.get("1h", []))
    research_eric = bool(config.get("swing", {}).get("research_overlay_enabled", False))
    if config.get("swing", {}).get("entry_gate_enabled", False):
        raise ValueError("Eric cannot be an entry gate in the pure five-step profile")
    eric_overlay = ({"status":"RESEARCH_ONLY_NOT_A_GATE",
                     "affects_decision":False,
                     "core_math":{tf:latest_d3(frames.get(tf, [])) for tf in INTERVALS}}
                    if research_eric else {"status":"DISABLED", "affects_decision":False})
    derivatives_result = derivatives(snapshot)
    fp = config.get("funding_research", {})
    funding_r = funding_regime(snapshot.get("funding_history"),
        int(datetime.fromisoformat(snapshot["fetched_at_utc"]).timestamp()*1000),
        lookback_days=int(fp.get("lookback_days",90)),
        min_samples=int(fp.get("min_samples",60)),
        extreme_percentile=float(fp.get("extreme_percentile",0.10)),
        streak_required=int(fp.get("consecutive_negative",3)))
    mandatory = ("1d", "4h", "1h")
    complete = all(summaries[tf]["status"] != "DATA_INSUFFICIENT" for tf in mandatory)
    if not complete:
        state = "DATA_INSUFFICIENT"
    else:
        state = "WAIT"  # External Pine parity and RTO validation not yet established.
    bias = ("BEAR" if summaries["1d"]["status"] == summaries["4h"]["status"] == "BEAR"
            else "BULL" if summaries["1d"]["status"] == summaries["4h"]["status"] == "BULL"
            else "MIXED_OR_NEUTRAL")
    return dict(engine="pure-five-step-research-0.4", repo_commit=repo_commit,
                exchange=snapshot.get("exchange"), market=snapshot.get("market"),
                symbol=snapshot.get("symbol"), fetched_at_utc=snapshot.get("fetched_at_utc"),
                data_errors=snapshot.get("errors", {}), decision=state, directional_context=bias,
                primary_method="PURE_FIVE_STEP",
                decision_reason=("Required 1D/4H/1H data incomplete" if state=="DATA_INSUFFICIENT" else
                                 "Research-only proxy; full execution signal is unverified"),
                trends=summaries, areas=areas, five_step_funnel=five_step,
                sweep_observations=candidates,
                candle_taker_delta=delta, derivatives=derivatives_result,
                funding_regime=funding_r, research_overlays={"eric":eric_overlay},
                pine_parity={"strong_support_resistance_v3_3":"UNKNOWN",
                             "eric_swing_v1_9_10":"UNKNOWN",
                             "liquidity_sweep_v1_1":"UNKNOWN"},
                risk=dict(trend_trade_max_fraction=config["risk"]["trend_trade_max_equity_fraction"],
                          countertrend_max_fraction=config["risk"]["countertrend_max_equity_fraction"]),
                caution="Research-only, pure five-step price-action proxy; Eric excluded from all entry/WAIT decisions; no auto execution")


def markdown_report(r: dict) -> str:
    """Present pure five-step first, without Eric in the default decision path."""
    lines = [f"# BTCUSDT｜纯五步交易漏斗 | {r.get('fetched_at_utc','unknown')}",
             "",
             f"- 数据/仓库版本：{r['repo_commit']}",
             f"- 市场：{r['exchange']} {r['market']} {r['symbol']}",
             f"- 主流程：{r.get('primary_method', 'PURE_FIVE_STEP')}",
             f"- 决策：**{r['decision']}**；原因：{r.get('decision_reason','研究模型未确认')}",
             "- 仅以已收盘K线和可获取成交/资金费率解释；原Pine信号未逐K验证，绝不自动下单。"]
    lines += ["", "## Step 1｜大周期结构（已收盘K）"]
    for tf in ("1w","1d","4h","1h","30m"):
        d = r["trends"][tf]
        lines.append(f"- {tf}：{d['status']}；收盘={d.get('close','UNKNOWN')}；EMA50={d.get('fast_ema','UNKNOWN')}；EMA200={d.get('slow_ema','UNKNOWN')}；K线结束={d.get('last_closed_bar_utc','UNKNOWN')}")
    lines.append(f"- 日线＋4H共同背景：**{r['directional_context']}**；趋势/区间并不保证方向。")

    lines += ["", "## Step 2｜已知流动性位置（前高/前低代理，非v3.3）"]
    for tf in ("1d","4h","1h"):
        a=r["areas"][tf]
        lines.append(f"- {tf}：{a.get('status','UNKNOWN')}；此前{a.get('lookback','?')}根已收盘K高={a.get('prior_high','UNKNOWN')}、低={a.get('prior_low','UNKNOWN')}；**不等于真实止损挂单分布**。")

    lines += ["", "## Step 3｜SH → BMS → RTO（纯价格结构代理）"]
    funnel=r.get("five_step_funnel",{})
    lines.append(f"- 模型状态：{funnel.get('status','UNKNOWN')}；确认BMS窗口={funnel.get('bms_confirm_window_bars','?')}根；RTO等待={funnel.get('rto_window_bars','?')}根；严格检查时间超限/扫盘失效。")
    for direction in ("LONG","SHORT"):
        e=funnel.get("latest_by_side",{}).get(direction)
        if not e:
            lines.append(f"- {direction}：近期无符合严格定义的SH。")
            continue
        lines.append(
            f"- {direction}：**{e['status']}**；SH结束={e['sweep_close_utc']}；"
            f"此前流动性参考={e['reference']}，扫盘极值={e['sweep_extreme']}；"
            f"BMS需要收盘突破={e['bms_level']}；"
            f"BMS={e.get('bms_close_utc') or '尚未确认'}；"
            f"RTO={e.get('rto_close_utc') or '尚未确认'}；"
            f"候选BMS截止={e['bms_deadline_utc']}。")
        if e["status"].startswith("EXPIRED") or e["status"].startswith("INVALIDATED"):
            lines.append(f"  - {direction}旧候选已失效/超时；后续上涨/下跌**不能事后补写**为旧信号成功。")
        if e["status"]=="CONFIRMED_RTO":
            lines.append(f"  - {direction} RTO已在历史K线上确认，但仅是代理事件；不等于现在可直接成交。")
    lines.append("- 尚无v1.1原始Pine逐K等价性，也未验证这些代理触发带来稳定盈利；**不自动产生买/卖信号**。")

    lines += ["", "## Step 4｜成交量 / OI / 已结算Funding反证"]
    delta=r["candle_taker_delta"]
    lines.append(f"- Binance K线taker方向：{delta.get('status')}，最近1H净Delta={delta.get('last_1h_delta_btc','UNKNOWN')} BTC，最近24H={delta.get('last_24h_net_delta_btc','UNKNOWN')} BTC（**不是逐笔CVD**）。")
    for key in ("oi","funding"):
        lines.append(f"- {key.upper()}：{json.dumps(r['derivatives'][key],ensure_ascii=False)}")
    fr=r.get("funding_regime",{})
    lines += [
        f"- 已结算Funding观察：{fr.get('status','UNKNOWN')} / {fr.get('regime','UNKNOWN')}；"
        f"最新费率={fr.get('last_rate_percent','UNKNOWN')}%；结算={fr.get('last_funding_time_utc','UNKNOWN')}；"
        f"连续负值={fr.get('negative_streak','UNKNOWN')}次；历史最低分位={fr.get('percentile_rank','UNKNOWN')}。",
        "- 负费率提示潜在逆向机会，但不是开多指令；OI不能推断哪一侧单独增仓。"]

    lines += ["", "## Step 5｜交易计划、失效与风险否决",
              "- **做多候选**：先定义已知低点附近新SH，随后在确认窗口内向上BMS，再等待RTO；以**新扫盘极值**及当时ATR确定失效位置。当前报告不声称已验证入场。",
              "- **做空候选**：已知高点附近新SH，随后向下BMS，再RTO；止损/目标必须与多头独立计算。",
              f"- 风险研究上限：顺势权益{100*r['risk']['trend_trade_max_fraction']:.2f}%，逆势权益{100*r['risk']['countertrend_max_fraction']:.2f}%；实际风险可能高于预设。",
              "- 没有已确认价、止损距离、可实现的净2R和成本复核时：**WAIT**，不追单。",
              "- 当前执行状态：**"+r["decision"]+"**（非交易指令）。"]
    if r.get("data_errors"):
        lines += ["", "## 数据缺口与获取异常"]
        for k,v in r["data_errors"].items():
            lines.append(f"- {k}：{v}")
    eric=r.get("research_overlays",{}).get("eric",{})
    if eric.get("status")=="RESEARCH_ONLY_NOT_A_GATE":
        lines += ["", "## 研究附录｜Eric D3（主动启用，完全不影响五步决策）"]
        for tf in ("1w","1d","4h","1h","30m"):
            d=eric["core_math"].get(tf,{})
            lines.append(f"- {tf}：{d.get('status','UNKNOWN')}；D3={d.get('d3','UNKNOWN')}")
        lines.append("- D3数学核心尚未与原Pine逐K一致性验收；未计算Episode/背离/反转。**不能参与入场/否决**。")
    return "\n".join(lines)+"\n"
