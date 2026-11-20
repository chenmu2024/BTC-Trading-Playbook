import unittest
from research.multiyear_event_study import load_years, research


class MultiYearFundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.evidence = load_years()
        cls.study = research()

    def test_complete_five_year_archive(self):
        self.assertEqual(len(self.data["klines"]), 42839)
        self.assertEqual(len(self.data["funding"]), 5355)
        self.assertEqual(len(self.evidence), 5)

    def test_expected_yearly_negative_count(self):
        counts = self.study["annual"]["counts"]
        self.assertEqual({k: counts[k]["negative"] for k in counts},
                         {"2022":242,"2023":111,"2024":92,"2025":141,"2026":232})

    def test_holdout_boundary_and_no_made_up_profit(self):
        s = self.study["train_vs_later"]
        self.assertEqual(s["split_test_start"], "2025-01-01T00:00:00+00:00")
        self.assertTrue(s["results"]["24"]["train"]["negative"]["n"] > 50)
        self.assertTrue(s["results"]["168"]["test"]["negative"]["n"] > 50)
        self.assertEqual(self.study["status"], "RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
