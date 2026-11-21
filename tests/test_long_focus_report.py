import unittest
from research.focus_long_report import FOCUS, SPLITS, analyze, markdown

class IndependentLongFocusTests(unittest.TestCase):
    def sample(self):
        results=[]
        trades={}
        for v in FOCUS:
            for split in SPLITS:
                row={"variant":v,"split":split,"trades":1,
                     "return_pct":0.2,"win_rate_pct":100,
                     "profit_factor":None,"max_intratrade_drawdown_pct":0.5,
                     "stops":0,"targets":1,
                     "rejected_stop_distance":0,"overlap_or_cooldown":0}
                results.append(row)
                key=v+"__"+split
                trades[key]=[{"side":1 if "_LONG_" in v else -1,"fee_cash":1.5,
                              "funding_cash":-0.2,"price_cash":20,"pnl":18.3,
                              "type":"TARGET","entry_time":1640995200000,
                              "exit_time":1641002400000}]
        return {"status":"RESEARCH_ONLY",
                "model":"Test exact event mock",
                "funding_streak3_rule":"The latest three ALREADY SETTLED rates, strictly prior to signal bar open.",
                "period":["2022-01-01","2026-11-20"],
                "results":results,"trades":trades}

    def test_all_focus_cohorts_are_own_accounts(self):
        report=analyze(self.sample())
        self.assertEqual(len(report["cohorts"]),len(FOCUS)*len(SPLITS))
        self.assertEqual(sum(v["trades"] for v in report["cohorts"]),len(FOCUS)*2)
        self.assertIn("手续费USDT",markdown(report))

    def test_reject_mixed_side(self):
        data=self.sample()
        data["trades"]["A_LONG_RTO__2022_2024"][0]["side"]=-1
        with self.assertRaisesRegex(ValueError,"mixed-side"):
            analyze(data)

    def test_reject_stale_protocol(self):
        data=self.sample()
        data["funding_streak3_rule"]="future settlement allowed"
        with self.assertRaises(ValueError):
            analyze(data)

if __name__=="__main__":
    unittest.main()
