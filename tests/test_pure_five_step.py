"""Tests for the deterministic pure five-step research path (no Eric gate)."""
import unittest

from engine.five_step import observe_funnel, atr_history
from engine.market import analyze, markdown_report


HOUR = 3_600_000


def bars(n=65):
    return [
        {"open_time_ms":i*HOUR,"close_time_ms":(i+1)*HOUR-1,
         "open":100.0,"high":101.0,"low":99.0,"close":100.0,
         "volume":100.0,"taker_buy_base":50.0}
        for i in range(n)
    ]


def settings():
    return {"lookback_bars":20,"average_volume_bars":20,"microstructure_lookback_bars":3,
            "confirm_bars":4,"retest_bars":5,"atr_period":14,
            "minimum_sweep_volume_ratio":0.8,
            "minimum_sweep_wick_fraction":0.3,
            "minimum_sweep_penetration_atr":0.1,"minimum_sweep_reclaim_atr":0.05,
            "minimum_bms_body_atr":0.2,
            "retest_touch_atr_above":0.15,"retest_touch_atr_below":0.35}


def long_sweep(a):
    i=len(a)
    a.append({**a[-1],"open_time_ms":i*HOUR,
              "close_time_ms":(i+1)*HOUR-1,"open":100.0,
              "high":102.0,"low":95.0,"close":100.0,"volume":230.0})


def extend(a, *, o=100., h=101., l=99., c=100.):
    i=len(a)
    a.append({**a[-1],"open_time_ms":i*HOUR,"close_time_ms":(i+1)*HOUR-1,
              "open":o,"high":h,"low":l,"close":c,"volume":120.0})


def event(a):
    """Select the ORIGINAL SH, not a new sweep on an invalidation bar."""
    out=observe_funnel(a,settings())
    matches=[x for x in out["events"] if x["sweep_index"]==65 and x["direction"]=="LONG"]
    assert len(matches)==1, out
    return matches[0]


class FunnelPriceActionTests(unittest.TestCase):
    def test_sweep_then_bms_then_retest(self):
        a=bars()
        long_sweep(a)
        self.assertEqual(event(a)["status"],"WAIT_BMS")
        extend(a,o=101,h=108,l=100,c=106)
        self.assertEqual(event(a)["status"],"WAIT_RTO")
        extend(a,o=103,h=105,l=102.1,c=104)
        x=event(a)
        self.assertEqual(x["status"],"CONFIRMED_RTO")
        self.assertTrue(x["is_recent_confirmation"])
        self.assertEqual(x["bms_level"],102.0)
        self.assertTrue(observe_funnel(a,settings())["not_a_trade_signal"])

    def test_bms_expiry_no_retroactive_confirmation(self):
        a=bars()
        long_sweep(a)
        for _ in range(4):
            extend(a)
        self.assertEqual(event(a)["status"],"EXPIRED_BMS")
        extend(a,o=101,h=110,l=100,c=108)
        self.assertEqual(event(a)["status"],"EXPIRED_BMS")

    def test_rto_expiry_no_retroactive_retest(self):
        a=bars()
        long_sweep(a)
        extend(a,o=101,h=108,l=100,c=106)
        for _ in range(5):
            extend(a,o=103,h=106,l=103,c=103)
        self.assertEqual(event(a)["status"],"EXPIRED_RTO")
        extend(a,o=103,h=105,l=102.1,c=104)
        self.assertEqual(event(a)["status"],"EXPIRED_RTO")

    def test_invalidation_takes_priority_over_breakout(self):
        a=bars()
        long_sweep(a)
        extend(a,o=101,h=110,l=94,c=106)
        self.assertEqual(event(a)["status"],"INVALIDATED_BEFORE_BMS")

    def test_invalid_after_bms_prevents_rto(self):
        a=bars()
        long_sweep(a)
        extend(a,o=101,h=108,l=100,c=106)
        extend(a,o=103,h=105,l=94,c=104)
        self.assertEqual(event(a)["status"],"INVALIDATED_BEFORE_RTO")

    def test_future_bars_cannot_change_past_sweep_reference(self):
        a=bars()
        long_sweep(a)
        first=event(a)
        extend(a,o=101,h=108,l=100,c=106)
        second=event(a)
        for k in ("sweep_close_utc","reference","sweep_extreme","bms_level"):
            self.assertEqual(first[k],second[k])

    def test_no_data_or_bad_config(self):
        self.assertEqual(observe_funnel(bars(5),settings())["status"],"DATA_INSUFFICIENT")
        with self.assertRaises(ValueError):
            observe_funnel(bars(),{**settings(),"confirm_bars":0})
        broken=bars()
        broken[-1]["open_time_ms"]+=1
        with self.assertRaisesRegex(ValueError,"contiguous"):
            observe_funnel(broken,settings())


class EricIndependenceTests(unittest.TestCase):
    def snapshot(self):
        b=bars(260)
        return {"market":"USD-M_PERPETUAL","exchange":"Binance","symbol":"BTCUSDT",
                "fetched_at_utc":"2026-11-21T00:00:00+00:00",
                "klines":{tf:b for tf in ("1w","1d","4h","1h","30m")},
                "oi":None,"funding":None,"errors":{}}

    def config(self,enabled):
        return {"trend":{"ema_fast":50,"ema_slow":200},
                "liquidity":settings(),
                "swing":{"research_overlay_enabled":enabled,"entry_gate_enabled":False},
                "risk":{"trend_trade_max_equity_fraction":.005,
                        "countertrend_max_equity_fraction":.0025}}

    def test_default_report_does_not_compute_or_display_eric(self):
        a=analyze(self.snapshot(),self.config(False),repo_commit="test")
        self.assertEqual(a["primary_method"],"PURE_FIVE_STEP")
        self.assertEqual(a["research_overlays"]["eric"]["status"],"DISABLED")
        self.assertNotIn("eric_core_math",a)
        self.assertNotIn("Eric D3",markdown_report(a))
        self.assertIn("Step 3",markdown_report(a))
        self.assertEqual(a["decision"],"WAIT")

    def test_eric_is_strictly_read_only_overlay(self):
        snapshot=self.snapshot()
        disabled=analyze(snapshot,self.config(False),repo_commit="test")
        enabled=analyze(snapshot,self.config(True),repo_commit="test")
        for key in ("decision","directional_context","five_step_funnel","risk","funding_regime"):
            self.assertEqual(disabled[key],enabled[key])
        self.assertEqual(enabled["research_overlays"]["eric"]["affects_decision"],False)
        self.assertIn("Eric D3",markdown_report(enabled))

    def test_no_eric_gate_allowed(self):
        config=self.config(False)
        config["swing"]["entry_gate_enabled"]=True
        with self.assertRaisesRegex(ValueError,"cannot be an entry gate"):
            analyze(self.snapshot(),config)


if __name__=="__main__":
    unittest.main()
