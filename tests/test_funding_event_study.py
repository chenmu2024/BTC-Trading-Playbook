import json
import unittest
from pathlib import Path

from research.funding_event_study import (
    costed_long, event_study, metrics, no_overlap, report_markdown,
    support_proxy, sweep_bms_proxy, validate, HOUR
)

FIXTURE = Path(__file__).resolve().parents[1] / "research/data/binance_btcusdt_2026-05-01_to_2026-11-20.json"


class EventStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.result = event_study(cls.data)

    def test_fixed_public_data_is_contiguous(self):
        bars, funds = validate(self.data)
        self.assertEqual(len(bars), 4895)
        self.assertEqual(len(funds), 615)

    def test_negative_24h_cohort_frozen_summary(self):
        d = self.result["results"]["24"]
        self.assertEqual(d["train"]["negative"]["n"], 40)
        self.assertEqual(d["test"]["negative"]["n"], 24)
        self.assertAlmostEqual(d["train"]["negative"]["mean_net_pct"], -0.677, delta=0.012)
        self.assertAlmostEqual(d["test"]["negative"]["mean_net_pct"], -0.249, delta=0.012)

    def test_negative_72h_and_168h_result(self):
        d72 = self.result["results"]["72"]["test"]["negative"]
        d168 = self.result["results"]["168"]["test"]["negative"]
        self.assertEqual(d72["n"], 24)
        self.assertEqual(d168["n"], 20)
        self.assertAlmostEqual(d72["mean_net_pct"], -1.629, delta=0.012)
        self.assertAlmostEqual(d168["mean_net_pct"], -1.064, delta=0.012)

    def test_filter_cohorts_are_tiny_and_none_both(self):
        d = self.result["results"]["24"]["test"]
        self.assertEqual(d["negative_near_72h_low"]["n"], 9)
        self.assertEqual(d["negative_sweep_bms_proxy"]["n"], 1)
        self.assertEqual(d["negative_both"]["n"], 0)
        self.assertEqual(d["negative_3"]["n"], 1)

    def test_costs_and_funding_receipts(self):
        bars = [[i*HOUR, 100, 101, 99, 100, 10] for i in range(30)]
        # Negative payment at t=4h means long receives a fixed-notional approximation.
        funds = [[4*HOUR, -0.001], [10*HOUR, 0.0002]]
        r = costed_long(bars, funds, 2, 12, .0006, .0002)
        self.assertAlmostEqual(r["gross"], 0)
        self.assertAlmostEqual(r["funding_receipt"], 0.0008)
        self.assertAlmostEqual(r["net"], -0.0008)

    def test_nonoverlap_does_not_double_book(self):
        events = [{"entry_time": 0, "exit_time": 5, "net": 0},
                  {"entry_time": 2, "exit_time": 8, "net": 0},
                  {"entry_time": 5, "exit_time": 9, "net": 0}]
        selected = no_overlap(events)
        self.assertEqual(len(selected), 2)

    def test_freeze_report_has_all_three_horizons(self):
        md = report_markdown(self.result)
        self.assertIn("| 24h |", md)
        self.assertIn("| 72h |", md)
        self.assertIn("| 168h |", md)
        self.assertIn("并非自动买入信号", md)

if __name__ == "__main__":
    unittest.main()
