import unittest
from research.five_step_observable_backtest import (
    HOUR, Variant, htf, ema, hourly_atr, matches, fill,
    generate_signals, research
)

def series(n=24*230):
    t=1640995200000
    return [[t+i*HOUR,100+i*.01,101+i*.01,99+i*.01,100+i*.01,80]
            for i in range(n)]

class FiveStepObservableTests(unittest.TestCase):
    def test_htf_uses_prior_complete_daily_candle_only(self):
        bars=series()
        out=htf(bars,24)
        self.assertEqual(out[24*220],out[24*220+23])
        self.assertEqual(out[24*225][0],1)

    def test_no_future_ema_and_atr(self):
        a=series(300)
        b=a+[[a[-1][0]+HOUR,1000,1010,990,1000,80]]
        self.assertEqual(ema([x[4] for x in a],50),
                         ema([x[4] for x in b],50)[:-1])
        self.assertEqual(hourly_atr(a),hourly_atr(b)[:-1])

    def test_long_short_funding_opposite_and_no_lookahead(self):
        bars=[[1640995200000+i*HOUR,100,101,99,100,80] for i in range(80)]
        funds=[[bars[4][0],-.001]]
        sig={"signal_index":1,"side":1,"phase":"RTO","extreme":96,"sweep_atr":5,
             "atr":5,"A":True,"B":False,"zone":False,"funding_rate":-.001,
             "funding_streak3":False}
        long=fill(sig,bars,funds,[funds[0][0]],[0,-.001],10000,.005)
        short=fill({**sig,"side":-1,"extreme":104},bars,funds,[funds[0][0]],[0,-.001],10000,.005)
        self.assertEqual(long["entry_time"],bars[2][0])
        self.assertGreater(long["funding_cash"],0)
        self.assertLess(short["funding_cash"],0)
        self.assertLess(long["pnl"],long["funding_cash"])

    def test_stop_filled_before_target_on_ambiguous_bar(self):
        bars=[[1640995200000+i*HOUR,100,101,99,100,80] for i in range(60)]
        bars[2][2]=120
        bars[2][3]=90
        sig={"signal_index":1,"side":1,"phase":"BMS","extreme":96,
             "sweep_atr":5,"atr":5}
        done=fill(sig,bars,[],[],[0],10000,.005)
        self.assertEqual(done["type"],"STOP")
        self.assertLess(done["pnl"],0)

    def test_funding_not_assumed_if_unknown(self):
        v=Variant("x","A","RTO","CONTRARIAN")
        s={"A":True,"B":False,"zone":True,"phase":"RTO",
           "side":1,"funding_rate":None,"funding_streak3":False}
        self.assertFalse(matches(s,v))
        self.assertTrue(matches(s,Variant("base","A","RTO","ANY")))
        s["funding_rate"]=-.0001
        self.assertTrue(matches(s,v))

    def test_real_archive_research_is_reproducible_and_research_only(self):
        from research.multiyear_event_study import load_years
        data,_=load_years()
        r=research(data)
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertEqual(r["bars"],42839)
        self.assertEqual(r["funding_records"],5355)
        self.assertEqual(len(r["results"]),16)
        self.assertTrue(all(x["by_side"]["LONG"]["count"]+x["by_side"]["SHORT"]["count"]==x["trades"] for x in r["results"]))
        self.assertTrue(r["signal_count"]>0)
        self.assertIn("historical OI",r["not_available"])
        self.assertIn("historical tick CVD",r["not_available"])

if __name__=="__main__":unittest.main()
