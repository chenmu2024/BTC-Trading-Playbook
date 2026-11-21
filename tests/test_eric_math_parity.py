import math
import unittest

from engine.eric_core import d3_history
from research.audit_tradingview_csv import compare_eric_d3


class EricMathCrossCheckTests(unittest.TestCase):
    @staticmethod
    def fixture():
        candles=[]
        rows=[]
        for i in range(700):
            close=50000+1200*math.sin(i/17)+350*math.sin(i/3.9)+i*0.2
            low=close-180.0
            rows.append([1700000000000+i*3600000,close,close+220,low,close,50])
            candles.append({"low":low,"close":close})
        output=d3_history(candles)
        export=[]
        for i,row in enumerate(rows):
            export.append({"open_time_ms":row[0],
                           "telemetry":{"ERIC_1h_D3":output[i]["d3"]}})
        ref={"symbol":"BTCUSDT","market":"USD-M_PERPETUAL","klines":rows}
        return ref,export

    def test_consistent_d3_matches_but_full_eric_parity_still_unknown(self):
        ref,export=self.fixture()
        result=compare_eric_d3(export,ref,minimum_comparison_bars=100)
        self.assertEqual(result["status"],"D3_MATH_MATCH")
        self.assertEqual(result["mismatch_count"],0)
        self.assertEqual(result["full_eric_algorithm_parity"],"NOT_TESTED")
        self.assertGreater(result["compared_bars"],100)

    def test_known_mismatch_is_detected(self):
        ref,export=self.fixture()
        index=600
        self.assertIsNotNone(export[index]["telemetry"]["ERIC_1h_D3"])
        export[index]["telemetry"]["ERIC_1h_D3"]+=0.5
        result=compare_eric_d3(export,ref,minimum_comparison_bars=100)
        self.assertEqual(result["status"],"D3_MATH_MISMATCH")
        self.assertEqual(result["mismatch_count"],1)

    def test_insufficient_data_never_claims_match(self):
        ref,export=self.fixture()
        result=compare_eric_d3(export[:250],ref,minimum_comparison_bars=100)
        self.assertEqual(result["status"],"INSUFFICIENT_DATA")


if __name__=="__main__":
    unittest.main()
