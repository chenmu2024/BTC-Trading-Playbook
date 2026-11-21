import unittest

from research.causal_structure_backtest import simulate_long, summarize_trades
from research.mtf_support_proxy import aggregate_4h, near_confirmed_support
from research.multiyear_event_study import load_years


class CausalStructureTests(unittest.TestCase):
    def test_zone_not_visible_before_confirmed(self):
        zones=[(100,200,50000.0,150.0)]
        self.assertFalse(near_confirmed_support(zones,99,50000,50))
        self.assertTrue(near_confirmed_support(zones,100,50000,50))
        self.assertFalse(near_confirmed_support(zones,200,50000,50))

    def test_4h_aggregation_uses_completed_chunks(self):
        rows=[[i*3600000,100,110,90,100,10] for i in range(11)]
        summary=aggregate_4h(rows)
        self.assertEqual(len(summary),2)
        self.assertEqual(summary[0]["last_hour_index"],3)

    def test_pessimistic_stop_wins_when_both_touched(self):
        rows=[[i*3600000,100,105,95,100,10] for i in range(40)]
        rows[11]=[11*3600000,100,125,87,100,10]
        signal={"confirm_idx":10,"phase":"BMS_RTO","sweep_extreme":90,
                "sweep_atr":5,"atr_entry_basis":10}
        r=simulate_long(signal,rows,[],[],[0.0])
        self.assertEqual(r["exit_kind"],"STOP")
        self.assertEqual(r["entry_time"],11*3600000)
        self.assertLess(r["net"],0)

    def test_max_exposure_capped_and_fee_positive(self):
        rows=[[i*3600000,100,105,95,100,10] for i in range(60)]
        rows[11]=[11*3600000,100,125,95,120,10]
        signal={"confirm_idx":10,"phase":"BMS_break","sweep_extreme":90,
                "sweep_atr":5,"atr_entry_basis":10}
        r=simulate_long(signal,rows,[],[],[0.0])
        self.assertEqual(r["exit_kind"],"TARGET")
        self.assertLessEqual(r["exposure_fraction"],0.95)
        self.assertGreater(r["net"],0)

    def test_real_data_is_research_only(self):
        from research.causal_structure_backtest import backtest
        data,_=load_years()
        r=backtest(data)
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertIn("sweeps",r["observations"])
        self.assertIn("results",r)
        self.assertGreater(r["observations"]["sweeps"],0)
        self.assertGreater(r["observations"]["bms"],0)


if __name__=="__main__":
    unittest.main()
