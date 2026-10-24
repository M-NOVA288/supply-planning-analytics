"""
End-to-end tests: run the full pipeline on the committed data, then check that
the MRP data-quality rules catch every injected problem and that the planning
logic and KPIs are internally consistent.

Run:  python3 -m unittest discover -s tests -v
"""
import csv
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PipelineTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls.tmp, "test.db")
        subprocess.run([sys.executable, os.path.join(ROOT, "python", "run_pipeline.py"),
                        "--db", cls.db, "--quiet"], check=True, capture_output=True)
        cls.con = sqlite3.connect(cls.db)

    def q(self, sql, *args):
        return self.con.execute(sql, args).fetchall()

    # ---------- MRP data quality ----------
    def test_every_injected_issue_is_caught(self):
        with open(os.path.join(ROOT, "data", "_injected_issues.csv")) as f:
            injected = list(csv.DictReader(f))
        self.assertGreater(len(injected), 0)
        missed = []
        for i in injected:
            found = self.q("""SELECT 1 FROM mrp_dq_issues
                              WHERE rule_id = ? AND matnr = ? AND werks = ?
                                AND (? = '' OR doc = ?)""",
                           i["rule_id"], i["matnr"], i["werks"], i["doc"], i["doc"])
            if not found:
                missed.append(i)
        self.assertEqual(missed, [], f"{len(missed)} injected issues not caught")

    def test_every_rule_fires(self):
        for (rule_id,) in self.q("SELECT rule_id FROM dq_rules"):
            n = self.q("SELECT COUNT(*) FROM mrp_dq_issues WHERE rule_id = ?", rule_id)[0][0]
            self.assertGreater(n, 0, f"{rule_id} found nothing")

    def test_no_false_positives_on_master_data_rules(self):
        """Rules DQ01-DQ05 only flag records the generator actually broke."""
        with open(os.path.join(ROOT, "data", "_injected_issues.csv")) as f:
            injected = {(r["rule_id"], r["matnr"], r["werks"]) for r in csv.DictReader(f)}
        flagged = set(self.q("""SELECT rule_id, matnr, werks FROM mrp_dq_issues
                                WHERE rule_id IN ('DQ01','DQ02','DQ03','DQ04','DQ05')"""))
        self.assertTrue(flagged <= injected, f"unexpected findings: {flagged - injected}")

    # ---------- planning logic ----------
    def test_one_availability_row_per_material_plant(self):
        rows, keys = self.q("""SELECT COUNT(*), COUNT(DISTINCT matnr || werks)
                               FROM zc_materialavailability""")[0]
        self.assertEqual(rows, keys)
        self.assertEqual(rows, self.q("SELECT COUNT(*) FROM marc")[0][0])

    def test_projected_stock_formula(self):
        for stock, po, daily, lt, proj in self.q(
                """SELECT stock, po_qty_in_lt, demand_daily, lead_time_days, projected_stock_end_lt
                   FROM zc_materialavailability"""):
            self.assertAlmostEqual(proj, round(stock + po - daily * max(lt, 1)), delta=1)

    def test_status_rules(self):
        bad = self.q("""SELECT COUNT(*) FROM zc_materialavailability
                        WHERE (availability_status = 'STOCKOUT' AND stock <> 0)
                           OR (availability_status = 'EXCESS' AND days_of_supply <= 180)
                           OR (availability_status = 'SHORTAGE_RISK' AND projected_stock_end_lt >= safety_stock)
                           OR (availability_status = 'NO_DEMAND' AND demand_daily <> 0)""")[0][0]
        self.assertEqual(bad, 0)

    # ---------- forecast ----------
    def test_three_month_forecast_for_every_series(self):
        series = self.q("SELECT COUNT(DISTINCT matnr || werks) FROM consumption")[0][0]
        self.assertEqual(self.q("SELECT COUNT(*) FROM forecast")[0][0], series * 3)
        self.assertEqual(self.q("SELECT COUNT(*) FROM forecast WHERE qty < 0")[0][0], 0)

    def test_chosen_model_never_worse_than_naive(self):
        worse = self.q("SELECT COUNT(*) FROM forecast_accuracy WHERE backtest_wape > naive_wape")[0][0]
        self.assertEqual(worse, 0)

    # ---------- KPIs ----------
    def test_kpis_in_valid_ranges(self):
        for row in self.q("""SELECT otif_pct, fill_rate_pct, excess_pct, dq_clean_pct, overdue_po_pct
                             FROM kpi_plant"""):
            for v in row:
                self.assertTrue(0 <= v <= 100, row)

    def test_inventory_value_reconciles(self):
        kpi = self.q("SELECT SUM(inventory_value) FROM kpi_plant")[0][0]
        raw = self.q("""SELECT SUM(d.labst * b.stprs) FROM mard d
                        JOIN mbew b ON b.matnr = d.matnr AND b.bwkey = d.werks""")[0][0]
        self.assertAlmostEqual(kpi, raw, delta=3)   # kpi rounds per plant

    def test_powerbi_exports_present(self):
        for f in ["dim_plant", "dim_material_plant", "fact_availability", "fact_dq_issues",
                  "fact_demand", "fact_deliveries", "kpi_plant"]:
            path = os.path.join(ROOT, "powerbi", "data", f"{f}.csv")
            self.assertTrue(os.path.getsize(path) > 0, f)


if __name__ == "__main__":
    unittest.main()
