import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from engine.market import parse_klines, ema, trend, levels, sweep_candidates, delta_summary, derivatives, analyze, markdown_report


def mkbars(n=260, price0=20000, increment=10):
    bars = []
    for i in range(n):
        price = price0 + increment * i
        bars.append(dict(open_time_ms=i*3600000, close_time_ms=(i+1)*3600000-1,
                         open=price, high=price+30, low=price-30, close=price,
                         volume=100.0, taker_buy_base=45.0))
    return bars


def config():
    return {"trend":{"ema_fast":50,"ema_slow":200},
            "liquidity":{"lookback_bars":20,"confirm_bars":4,"minimum_sweep_volume_ratio":0.8},
            "risk":{"trend_trade_max_equity_fraction":0.005,"countertrend_max_equity_fraction":0.0025}}


class PublicDataTests(unittest.TestCase):
    def test_unclosed_bar_discarded(self):
        def row(t):
            return [t, "100", "110", "90", "100", "20", t+999, "0", 1, "8", "0", "0"]
        self.assertEqual(len(parse_klines([row(0),row(1000)], 1100)), 1)
        self.assertEqual(parse_klines([row(0),row(1000)], 1100)[0]["close_time_ms"],999)

    def test_duplicate_rejected(self):
        row=[0,"100","110","90","100","20",999,"0",1,"8","0"]
        with self.assertRaises(ValueError):
            parse_klines([row,row], 3000)

    def test_ema_and_trend(self):
        self.assertAlmostEqual(ema([1.0]*300, 50), 1.0)
        b=mkbars()
        self.assertEqual(trend(b)["status"],"BULL")
        self.assertEqual(trend(b[:150])["status"],"DATA_INSUFFICIENT")

    def test_prior_levels_do_not_include_last_bar(self):
        b=mkbars(25,1000,0)
        b[-1]["high"]=5000
        b[-1]["low"]=1
        self.assertEqual(levels(b,20)["prior_high"],1030)
        self.assertEqual(levels(b,20)["prior_low"],970)

    def test_sweep_candidate_and_invalidation(self):
        b=mkbars(60,1000,0)
        b[-1].update(low=900,close=1020,high=1030)
        cases=sweep_candidates(b,20,4,0.8)
        self.assertEqual(cases[-1]["direction"],"LONG")
        self.assertEqual(cases[-1]["stage"],"SWEEP_CANDIDATE_WAIT_BMS")
        b.append(dict(b[-1], open_time_ms=60*3600000, close_time_ms=61*3600000-1,low=899,close=900))
        self.assertEqual(sweep_candidates(b,20,4,0.8)[-1]["stage"],"INVALID")

    def test_taker_delta_explicit_units(self):
        d=delta_summary(mkbars(30))
        self.assertEqual(d["last_1h_delta_btc"], -10.0)
        self.assertEqual(d["last_24h_net_delta_btc"], -240.0)

    def test_oi_funding_missing_is_not_zero(self):
        d=derivatives({"oi":None,"funding":None})
        self.assertEqual(d["oi"]["status"],"UNKNOWN")
        self.assertEqual(d["funding"]["status"],"UNKNOWN")

    def test_offline_cli_saves_valid_audit_snapshot(self):
        bars = mkbars()
        snap = {"market":"USD-M_PERPETUAL","exchange":"Binance","symbol":"BTCUSDT",
                "fetched_at_utc":"2026-11-21T00:00:00+00:00",
                "klines":{tf:bars for tf in ("1w","1d","4h","1h","30m")},
                "oi":None,"funding":None,"errors":{}}
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            inp = Path(folder) / "input.json"
            inp.write_text(json.dumps(snap), encoding="utf-8")
            out = Path(folder) / "out"
            proc = subprocess.run([sys.executable,"-m","engine.cli","--config","config/strategy.yaml",
                                   "--snapshot-file",str(inp),"--output-dir",str(out)],
                                   cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            saved = list(out.glob("*.snapshot.json"))
            self.assertEqual(len(saved),1)
            decoded = json.loads(saved[0].read_text(encoding="utf-8"))
            self.assertEqual(decoded["symbol"],"BTCUSDT")
            self.assertEqual(len(list(out.glob("*.md"))),1)
            self.assertEqual(len(list(out.glob("BTCUSDT_*.json"))),2)

    def test_report_does_not_invent_pine_signals(self):
        b=mkbars()
        snap={"market":"USD-M_PERPETUAL","exchange":"Binance","symbol":"BTCUSDT",
              "fetched_at_utc":"2026-11-21T00:00:00+00:00",
              "klines":{tf:b for tf in ("1w","1d","4h","1h","30m")},
              "oi":None,"funding":None,"errors":{}}
        result=analyze(snap,config(),repo_commit="testsha")
        self.assertEqual(result["decision"],"WAIT")
        self.assertEqual(result["pine_parity"]["eric_swing_v1_9_10"],"UNKNOWN")
        self.assertIn("不是逐笔CVD",markdown_report(result))


if __name__ == "__main__":
    unittest.main()
