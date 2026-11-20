import unittest
from engine.funding import funding_regime, HOUR, DAY

def sample(rates, hours=8, end=90*DAY):
    return [{"fundingTime": end-(len(rates)-1-i)*hours*HOUR, "fundingRate": str(v)}
            for i,v in enumerate(rates)]

class FundingTests(unittest.TestCase):
    def test_empty_unknown(self):
        self.assertEqual(funding_regime([], 90*DAY)["status"], "UNKNOWN")

    def test_first_negative_watch_only(self):
        a = funding_regime(sample([0.0001]*80+[-0.0001]), 90*DAY)
        self.assertEqual(a["regime"], "NEGATIVE_WATCH")
        self.assertEqual(a["negative_streak"], 1)
        self.assertFalse(a["long_entry_signal"])

    def test_extreme_negative_not_buy(self):
        a = funding_regime(sample([0.0001]*80+[-0.0006,-0.0007,-0.0008]), 90*DAY)
        self.assertEqual(a["regime"], "DEEP_NEGATIVE_WATCH")
        self.assertLessEqual(a["percentile_rank"], 0.1)
        self.assertFalse(a["long_entry_signal"])

    def test_positive_no_reverse_watch(self):
        a = funding_regime(sample([-0.0001]*75+[0.0001]), 90*DAY)
        self.assertEqual(a["regime"], "NON_NEGATIVE")

    def test_no_fake_percentile_when_few(self):
        a = funding_regime(sample([-0.0001]*5), 90*DAY)
        self.assertIsNone(a["percentile_rank"])
        self.assertEqual(a["regime"], "PERSISTENT_NEGATIVE_WATCH")

    def test_stale_and_future(self):
        a = funding_regime(sample([-0.0001]*75), 90*DAY+4*DAY)
        self.assertIn(a["status"], ["UNKNOWN","STALE"])
        history=sample([0.0001]*75)
        history.append({"fundingTime":90*DAY+8*HOUR,"fundingRate":"-0.01"})
        a = funding_regime(history, 90*DAY+1)
        self.assertEqual(a["regime"],"NON_NEGATIVE")

    def test_normalized_variable_intervals(self):
        rows=[{"fundingTime":100*HOUR,"fundingRate":"0.0001"},
              {"fundingTime":104*HOUR,"fundingRate":"-0.0001"},
              {"fundingTime":105*HOUR,"fundingRate":"-0.0002"}]
        a=funding_regime(rows,105*HOUR,min_samples=2)
        self.assertAlmostEqual(a["last_8h_equivalent_percent"],-0.16)

if __name__ == "__main__":
    unittest.main()
