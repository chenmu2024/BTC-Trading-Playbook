import math
import unittest
from engine.eric_core import d3_history, latest_d3


def candles(values):
    return [{"low":v-0.7,"close":v,"high":v+0.8} for v in values]


class EricD3CoreTests(unittest.TestCase):
    def test_short_history_not_ready(self):
        result=latest_d3(candles([100.0]*15))
        self.assertEqual(result["status"],"CORE_NOT_READY")

    def test_oscillating_prices_d3_finite_centered(self):
        seq=[100+8*math.sin(i*0.17)+2*math.cos(i*0.67)+i*0.01 for i in range(300)]
        r=d3_history(candles(seq))
        self.assertIsNone(r[0]["d3"])
        self.assertTrue(r[-1]["core_ready"])
        self.assertTrue(-50.0001<=r[-1]["d3"]<=50.0001)
        self.assertTrue(0<=r[-1]["rsi"]<=100)
        latest=latest_d3(candles(seq))
        self.assertEqual(latest["status"],"CORE_FORMULA_PORT_UNVERIFIED")
        self.assertFalse(latest["verified_against_pine_csv"])

    def test_no_future_leakage_per_bar(self):
        seq=[100+8*math.sin(i*0.19)+i*0.04 for i in range(150)]
        before=d3_history(candles(seq))
        after=d3_history(candles(seq+[10000,1,100,103]))
        for i in range(len(before)):
            a,b=before[i]["d3"],after[i]["d3"]
            self.assertEqual(a is None,b is None)
            if a is not None:
                self.assertAlmostEqual(a,b,places=10)

    def test_flat_interval_suppresses_stale_oscillator(self):
        seq=[100+10*math.sin(i*0.2) for i in range(100)]
        seq+= [103.0]*120
        r=d3_history(candles(seq))
        self.assertFalse(r[-1]["core_ready"])
        self.assertIsNone(r[-1]["d3"])

    def test_parameter_and_input_guards(self):
        with self.assertRaises(ValueError):
            d3_history(candles([100]*10),rsi_len=1)
        with self.assertRaises(ValueError):
            d3_history([{"low":102,"close":100}])


if __name__=="__main__":
    unittest.main()
