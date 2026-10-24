#!/usr/bin/env python3
"""
End-to-end supply planning analytics run:

  1. Load the SAP-shaped extracts into a local database
  2. Forecast demand by material and plant (python/forecast.py)
  3. Build the planning views, MRP data-quality findings and KPI scorecard (sql/)
  4. Export a star schema for Power BI (powerbi/data/) and a dashboard preview

Usage:
    python3 python/run_pipeline.py [--as-of 2026-10-01] [--db output/planning.db]
"""
import argparse
import csv
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import forecast  # noqa: E402

TABLES = ["t001w", "mara", "marc", "mard", "mbew", "ekpo", "plaf", "consumption", "deliveries"]


def run_sql_file(con, path, show=True):
    """Execute each statement; print any result sets."""
    buf = ""
    with open(path) as f:
        for line in f:
            buf += line
            if sqlite3.complete_statement(buf):
                stmt, buf = buf.strip(), ""
                if not any(l.strip() and not l.strip().startswith("--") for l in stmt.splitlines()):
                    continue
                cur = con.execute(stmt)
                if cur.description and show:
                    print_table([d[0] for d in cur.description], cur.fetchall())
    con.commit()


def print_table(cols, rows, limit=20):
    rows = [["" if v is None else str(v) for v in r] for r in rows]
    w = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(x) for c, x in zip(cols, w)))
    print("  ".join("-" * x for x in w))
    for r in rows[:limit]:
        print("  ".join(v.ljust(x) for v, x in zip(r, w)))
    print()


def load(con, data_dir):
    with open(os.path.join(ROOT, "sql", "01_tables.sql")) as f:
        con.executescript(f.read())
    for t in TABLES:
        with open(os.path.join(data_dir, f"{t}.csv"), newline="") as f:
            r = csv.reader(f)
            header = next(r)
            rows = [[None if v == "" and h not in ("lvorm", "dispo") else v
                     for h, v in zip(header, row)] for row in r]
        con.executemany(f"INSERT INTO {t} ({','.join(header)}) VALUES ({','.join('?' * len(header))})", rows)
    con.commit()


def export(con, query, path):
    cur = con.execute(query)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow([d[0] for d in cur.description])
        w.writerows(cur.fetchall())


def export_powerbi(con, out):
    """Star schema: two dimensions, four facts. Relationships in powerbi/MODEL.md."""
    os.makedirs(out, exist_ok=True)
    export(con, "SELECT werks, name1 AS plant_name, ort01 AS city FROM t001w", f"{out}/dim_plant.csv")
    export(con, """SELECT matnr || '|' || werks AS material_plant_key, matnr, werks, maktx, mtart, matkl,
                          maabc, dispo, dismm, disls, beskz, lead_time_days, safety_stock, std_price,
                          CASE WHEN lvorm = 'X' THEN 1 ELSE 0 END AS flagged_for_deletion
                   FROM zi_plantmaterial""", f"{out}/dim_material_plant.csv")
    export(con, """SELECT matnr || '|' || werks AS material_plant_key, werks, stock, stock_value,
                          demand_monthly, ROUND(demand_daily, 2) AS demand_daily, days_of_supply,
                          open_po_qty, overdue_po_qty, po_qty_in_lt, planned_order_qty,
                          projected_stock_end_lt, availability_status
                   FROM zc_materialavailability""", f"{out}/fact_availability.csv")
    export(con, """SELECT i.matnr || '|' || i.werks AS material_plant_key, i.werks, i.rule_id,
                          r.rule_name, r.severity, i.doc, i.detail
                   FROM mrp_dq_issues i JOIN dq_rules r USING (rule_id)""", f"{out}/fact_dq_issues.csv")
    export(con, """SELECT matnr || '|' || werks AS material_plant_key, werks, period, qty, 'Actual' AS series
                   FROM consumption
                   UNION ALL
                   SELECT matnr || '|' || werks, werks, period, qty, 'Forecast'
                   FROM forecast""", f"{out}/fact_demand.csv")
    export(con, """SELECT vbeln, matnr || '|' || werks AS material_plant_key, werks, req_date, gi_date,
                          order_qty, delivered_qty,
                          CASE WHEN gi_date <= req_date AND delivered_qty = order_qty THEN 1 ELSE 0 END AS otif_flag
                   FROM deliveries""", f"{out}/fact_deliveries.csv")
    export(con, "SELECT * FROM kpi_plant", f"{out}/kpi_plant.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-10-01")
    ap.add_argument("--db", default=os.path.join(ROOT, "output", "planning.db"))
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    os.makedirs(os.path.dirname(a.db), exist_ok=True)
    if os.path.exists(a.db):
        os.remove(a.db)
    con = sqlite3.connect(a.db)

    load(con, a.data)
    con.execute("INSERT INTO run_params VALUES (?, 90, 180)", (a.as_of,))
    print(f"Loaded extracts into {a.db}")

    picks = forecast.run(con)
    print(f"Forecast models selected: {dict(sorted(picks.items()))}\n")

    for f in ["02_planning_views.sql", "03_mrp_data_quality.sql", "04_kpis.sql"]:
        print(f"== {f}")
        run_sql_file(con, os.path.join(ROOT, "sql", f), show=not a.quiet)

    export_powerbi(con, os.path.join(ROOT, "powerbi", "data"))
    print("Power BI star schema written to powerbi/data/")

    try:
        import dashboard
        dashboard.render(con, os.path.join(ROOT, "docs", "dashboard_preview.png"))
        print("Dashboard preview written to docs/dashboard_preview.png")
    except ImportError as e:
        print(f"Skipping dashboard preview ({e})")

    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
