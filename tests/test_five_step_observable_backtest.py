import unittest
from research.five_step_observable_backtest import (
    HOUR, Variant, htf, ema, hourly_atr, matches, fill,
    generate_signals, research, funding_at_signal
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


    def test_consecutive_funding_uses_only_three_past_settlements(self):
        times=[0,8*HOUR,16*HOUR,24*HOUR]
        rates=[[times[0],-.001],[times[1],-.001],[times[2],-.001],[times[3],+.03]]
        # Positive future settlement must not invalidate previous negative streak.
        rate,streak=funding_at_signal(rates,times,20*HOUR,side=1)
        self.assertEqual(rate,-.001)
        self.assertTrue(streak)
        # Before third negative settlement, three-observation test is false.
        self.assertFalse(funding_at_signal(rates,times,16*HOUR,1)[1])
        # Once the positive future settlement has passed, negative streak is broken.
        self.assertFalse(funding_at_signal(rates,times,25*HOUR,1)[1])
        self.assertTrue(funding_at_signal(rates,times,25*HOUR,-1)[0]>0)
        self.assertEqual(funding_at_signal(rates,times,100*HOUR,1),(None,False))

    def test_direction_filter_must_be_enforced(self):
        long_signal={"A":True,"B":False,"zone":False,"phase":"RTO","side":1,
                     "funding_rate":-.001,"funding_streak3":True}
        self.assertTrue(matches(long_signal,Variant("x","A","RTO","ANY",False,1)))
        self.assertFalse(matches(long_signal,Variant("x","A","RTO","ANY",False,-1)))
        self.assertTrue(matches(long_signal,Variant("x","A","RTO","ANY",False,0)))

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
        self.assertEqual(len(r["results"]),34)
        self.assertTrue(all(x["by_side"]["LONG"]["count"]+x["by_side"]["SHORT"]["count"]==x["trades"] for x in r["results"]))
        self.assertTrue(r["signal_count"]>0)
        self.assertIn("historical OI",r["not_available"])
        self.assertIn("historical tick CVD",r["not_available"])
        funnel=r["candidate_funnel_by_year"]
        self.assertEqual(len(funnel),5*2*2*2)
        self.assertTrue(all(0<=row["geometry_valid"]<=row["event_count"] for row in funnel))
        self.assertTrue(all(0<=row["contrarian_funding"]<=row["event_count"] for row in funnel))
        self.assertTrue(all(0<=row["streak3"]<=row["contrarian_funding"] for row in funnel))
        a={x["variant"]+"__"+x["split"]:x for x in r["results"]}
        for phase in ("A_LONG_RTO","B_LONG_RTO","B_LONG_RTO_NEG","A_SHORT_RTO"):
            for split in ("2022_2024","2025_2026"):
                self.assertIn(phase+"__"+split,a)
        for v in r["results"]:
            if "_LONG_" in v["variant"]:
                self.assertEqual(v["by_side"]["SHORT"]["count"],0)
            if "_SHORT_" in v["variant"]:
                self.assertEqual(v["by_side"]["LONG"]["count"],0)

if __name__=="__main__":unittest.main()
