import csv
import json
import tempfile
import unittest
from pathlib import Path

from research.audit_tradingview_csv import (
    REQUIRED, audit, load_csv, matching_column, time_ms
)


class CsvPineExportTests(unittest.TestCase):
    def sample(self):
        keys=REQUIRED["sr"]
        columns=["Time","Open","High","Low","Close"]+[f"SR EXPORT: {v}" for v in keys]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"tv.csv"
            with open(path,"w",encoding="utf-8",newline="") as out:
                w=csv.writer(out)
                w.writerow(columns)
                for i in range(2):
                    vals=[None]*len(keys)
                    for j,key in enumerate(keys):
                        if "source_close_unix_s" in key:
                            vals[j]=1700000000+i*3600+3600
                        else:
                            vals[j]=100
                    w.writerow([1700000000+i*3600,100,101,99,100,*vals])
            yield load_csv(path,"sr")

    def test_valid_csv_and_matching_reference(self):
        rows=next(self.sample())
        ref={"symbol":"BTCUSDT","market":"USD-M_PERPETUAL",
             "klines":[[1700000000000+i*3600000,100,101,99,100,50] for i in range(2)]}
        result=audit(rows,ref,"sr",min_matches=2)
        self.assertEqual(result["status"],"CHART_DATA_VALIDATED")
        self.assertEqual(result["pine_algorithm_parity"],"NOT_TESTED")
        self.assertEqual(result["matched_bars"],2)

    def test_price_mismatch_flagged(self):
        rows=next(self.sample())
        rows[0]["close"]=102.0
        ref={"symbol":"BTCUSDT","market":"USD-M_PERPETUAL",
             "klines":[[1700000000000+i*3600000,100,101,99,100,50] for i in range(2)]}
        result=audit(rows,ref,"sr",min_matches=2)
        self.assertEqual(result["status"],"CHART_DATA_MISMATCH")
        self.assertEqual(result["ohlc_mismatch_total"],1)

    def test_future_source_timestamp_flagged(self):
        rows=next(self.sample())
        rows[0]["telemetry"]["SR_4h_source_close_unix_s"]=1900000000
        ref={"symbol":"BTCUSDT","market":"USD-M_PERPETUAL",
             "klines":[[1700000000000+i*3600000,100,101,99,100,50] for i in range(2)]}
        result=audit(rows,ref,"sr",min_matches=2)
        self.assertEqual(result["future_source_time_violation_total"],1)
        self.assertEqual(result["status"],"CHART_DATA_MISMATCH")

    def test_missing_duplicate_indicator_telemetry_rejected(self):
        with self.assertRaisesRegex(ValueError,"Expected one column"):
            matching_column(["foo","bar"],"SR_1h_support_center")
        with self.assertRaisesRegex(ValueError,"Expected one column"):
            matching_column(["SR_1h_support_center","a SR_1h_support_center"],"SR_1h_support_center")

    def test_timezones_must_be_explicit(self):
        self.assertEqual(time_ms("1700000000"),1700000000000)
        self.assertEqual(time_ms("2023-11-14T22:13:20+00:00"),1700000000000)
        with self.assertRaisesRegex(ValueError,"Timezone-naive"):
            time_ms("2023-11-14T22:13:20")
        self.assertEqual(time_ms("2023-11-14T22:13:20",assume_utc=True),1700000000000)


class TelemetryCopiesTests(unittest.TestCase):
    ROOT=Path(__file__).resolve().parents[1]/"pine"

    def test_original_strong_indicator_engine_unchanged(self):
        original=(self.ROOT/"strong_support_resistance_v3_3.pine").read_text(encoding="utf-8")
        sidecar=(self.ROOT/"validation/strong_support_resistance_v3_3_export.pine").read_text(encoding="utf-8")
        expected=original.replace(
            'indicator("多周期强支撑强压力 v3.3", shorttitle="Strong MTF SR 3.3",',
            'indicator("多周期强支撑压力 v3.3 PARITY EXPORT", shorttitle="SRv33EXPORT",'
        )
        self.assertEqual(sidecar.split("\n// VERIFICATION COPY ONLY:")[0].strip().split("\n// ---")[0], expected.strip().split("\n// ---")[0])

    def test_eric_and_sweep_copies_contain_original_logic(self):
        for original_name, export_name, phrase in [
            ("eric_swing_filter_v1_9_10.pine","validation/eric_swing_filter_v1_9_10_export.pine",
             'indicator("Eric Swing Filter · v1.9.10 Readable Signals", shorttitle="EricSw1910",'),
            ("liquidity_sweep_v1_1_diagnostic.pine","validation/liquidity_sweep_v1_1_export.pine",
             'strategy("5-Step Liquidity Sweep | Diagnostic V1.1",')
        ]:
            original=(self.ROOT/original_name).read_text(encoding="utf-8")
            sidecar=(self.ROOT/export_name).read_text(encoding="utf-8")
            if "eric_" in original_name:
                expected=original.replace(phrase,
                    'indicator("Eric Swing Filter v1.9.10 PARITY EXPORT", shorttitle="Eric1910CSV",')
            else:
                expected=original.replace(phrase,
                    'strategy("5-Step Liquidity Sweep | Diagnostic V1.1 PARITY EXPORT",')
            self.assertTrue(sidecar.startswith(expected))
            self.assertGreater(len(sidecar),len(expected))


if __name__=="__main__":
    unittest.main()
