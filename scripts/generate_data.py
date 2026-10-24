#!/usr/bin/env python3
"""
Generate a synthetic supply planning dataset shaped like SAP S/4HANA tables.

Table and field names follow SAP conventions (MARA, MARC, MARD, MBEW, EKPO/EKET,
PLAF) so the SQL reads the way it would against an S/4 system or its CDS views.
All data is fake. Known MRP master-data problems are injected on purpose, and the
injected keys are written to data/_injected_issues.csv so tests can prove every
check catches them.

Usage:
    python3 scripts/generate_data.py [--seed 7] [--out data]
"""
import argparse
import csv
import math
import os
import random
from datetime import date, timedelta

AS_OF = date(2026, 10, 1)        # planning run date
HISTORY_MONTHS = 24

PLANTS = [  # werks, name, city
    ("1000", "Houston DC", "Houston, TX"),
    ("2000", "Charlotte Plant", "Charlotte, NC"),
    ("3000", "Rosemont DC", "Rosemont, IL"),
]
VENDORS = [f"V{n}" for n in range(30001, 30021)]

# material families for a safety and environmental products business
FAMILIES = [  # (matkl, description stem, type, base price, base monthly demand)
    ("GASDET", "Portable Gas Detector", "FERT", 410.0, 60),
    ("SENSOR", "Gas Sensor Module", "HALB", 95.0, 180),
    ("RESPCT", "Respirator Cartridge", "FERT", 18.5, 900),
    ("HARNES", "Fall Protection Harness", "FERT", 145.0, 120),
    ("GLOVES", "Cut-Resistant Gloves (pair)", "FERT", 9.75, 1500),
    ("PCBASM", "Detector PCB Assembly", "HALB", 62.0, 200),
    ("BATTRY", "Li-ion Battery Pack", "ROH", 24.0, 350),
    ("HOUSNG", "Polycarbonate Housing", "ROH", 6.4, 400),
    ("CALGAS", "Calibration Gas Cylinder", "FERT", 78.0, 90),
    ("EYEWR", "Safety Eyewear", "FERT", 7.2, 1100),
]


def month_starts(end, n):
    """First day of each of the n months before `end` (oldest first)."""
    out, y, m = [], end.year, end.month
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(date(y, m, 1))
    return out[::-1]


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)

    mara, marc, mard, mbew, ekpo, plaf, consumption, deliveries = ([] for _ in range(8))
    injected = []                 # (rule_id, matnr, werks, key)
    months = month_starts(AS_OF, HISTORY_MONTHS)
    po_no, del_no, plnum = 4500000001, 80000001, 10000001

    n_mat = 0
    for matkl, stem, mtart, base_price, base_dem in FAMILIES:
        for v in range(1, 16):    # 15 variants per family -> 150 materials
            n_mat += 1
            matnr = f"M{100000 + n_mat}"
            deleted = "X" if rng.random() < 0.04 else ""
            mara.append([matnr, f"{stem} v{v}", mtart, matkl, "EA", deleted])
            price = round(base_price * rng.uniform(0.7, 1.4), 2)

            for werks, _, _ in PLANTS:
                if rng.random() < 0.25:          # not every material at every plant
                    continue
                abc = rng.choices("ABC", weights=[20, 30, 50])[0]
                beskz = "E" if mtart == "HALB" and werks == "2000" else "F"
                plifz = rng.choice([7, 10, 14, 21, 28, 35, 45]) if beskz == "F" else 0
                dzeit = rng.choice([3, 5, 7]) if beskz == "E" else 0
                dismm = "PD"
                disls = rng.choice(["EX", "EX", "HB", "FX"])
                bstfe = rng.choice([100, 250, 500, 1000]) if disls == "FX" else 0
                dispo = rng.choice(["P01", "P02", "P03", "P04"])
                demand = base_dem * rng.uniform(0.3, 1.6) * (1.6 if abc == "A" else 1 if abc == "B" else 0.5)
                eisbe = int(demand * rng.uniform(0.25, 0.6))

                # ---- injected MRP master-data problems ----
                r = rng.random()
                if r < 0.05 and beskz == "F":
                    plifz = 0; injected.append(("DQ01", matnr, werks, ""))
                elif r < 0.09 and abc == "A":
                    eisbe = 0; injected.append(("DQ02", matnr, werks, ""))
                elif r < 0.12:
                    disls, bstfe = "FX", 0; injected.append(("DQ03", matnr, werks, ""))
                elif r < 0.15:
                    dispo = ""; injected.append(("DQ04", matnr, werks, ""))
                elif r < 0.18:
                    dismm = "ND"; injected.append(("DQ05", matnr, werks, ""))

                marc.append([matnr, werks, dismm, dispo, disls, bstfe, plifz, dzeit,
                             eisbe, beskz, abc])
                mbew.append([matnr, werks, price, "S"])

                # ---- monthly consumption with trend + seasonality + noise ----
                trend = rng.uniform(-0.015, 0.025)
                season_amp = rng.uniform(0.0, 0.35)
                intermittent = rng.random() < 0.1
                hist = []
                for i, m in enumerate(months):
                    lvl = demand * (1 + trend) ** i
                    s = 1 + season_amp * math.sin(2 * math.pi * (m.month - 3) / 12)
                    q = max(0.0, rng.gauss(lvl * s, lvl * 0.18))
                    if intermittent and rng.random() < 0.5:
                        q = 0.0
                    hist.append(int(round(q)))
                    consumption.append([matnr, werks, m.isoformat(), hist[-1]])
                avg_recent = sum(hist[-3:]) / 3 if hist else 0

                # ---- stock: mostly healthy, some short, some excess ----
                cover_days = rng.choices([5, 20, 45, 75, 120, 240], weights=[6, 22, 34, 24, 9, 5])[0]
                labst = int(avg_recent / 30 * cover_days * rng.uniform(0.8, 1.2))
                if deleted:
                    labst = int(labst * 0.3)
                mard.append([matnr, werks, "0001", labst, int(labst * rng.uniform(0, 0.05))])

                # ---- open purchase orders (EKPO/EKET) ----
                if beskz == "F" and dismm != "ND":
                    for _ in range(rng.randint(0, 3)):
                        qty = max(10, int(avg_recent * rng.uniform(0.5, 1.5)))
                        eindt = AS_OF + timedelta(days=rng.randint(-20, -1) if rng.random() < 0.10
                                                   else rng.randint(1, 60))
                        recv = 0
                        ekpo.append([po_no, 10, matnr, werks, rng.choice(VENDORS),
                                     qty, recv, eindt.isoformat(), price])
                        if eindt < AS_OF:
                            injected.append(("DQ06", matnr, werks, str(po_no)))
                        po_no += 1
                if deleted and beskz == "F":       # open PO on a material flagged for deletion
                    ekpo.append([po_no, 10, matnr, werks, rng.choice(VENDORS),
                                 50, 0, (AS_OF + timedelta(days=20)).isoformat(), price])
                    injected.append(("DQ08", matnr, werks, str(po_no)))
                    po_no += 1

                # ---- planned orders (PLAF), some past due and never converted ----
                for _ in range(rng.randint(0, 2)):
                    psttr = AS_OF + timedelta(days=rng.randint(-15, -1) if rng.random() < 0.08
                                                  else rng.randint(1, 45))
                    plaf.append([plnum, matnr, werks, max(10, int(avg_recent * 0.6)),
                                 psttr.isoformat(), (psttr + timedelta(days=max(plifz, dzeit, 1))).isoformat(),
                                 "NB" if beskz == "F" else "LA"])
                    if psttr < AS_OF:
                        injected.append(("DQ07", matnr, werks, str(plnum)))
                    plnum += 1

                # ---- outbound deliveries last 90 days, for OTIF and fill rate ----
                if mtart == "FERT":
                    short_prone = cover_days <= 20
                    for _ in range(rng.randint(4, 12)):
                        req = AS_OF - timedelta(days=rng.randint(1, 90))
                        oq = max(1, int(avg_recent / 10 * rng.uniform(0.5, 1.5)))
                        late = rng.random() < (0.22 if short_prone else 0.05)
                        short = rng.random() < (0.15 if short_prone else 0.02)
                        dq = int(oq * rng.uniform(0.5, 0.95)) if short else oq
                        act = req + timedelta(days=rng.randint(1, 6) if late else 0)
                        deliveries.append([del_no, matnr, werks, req.isoformat(),
                                           act.isoformat(), oq, dq])
                        del_no += 1

    write(f"{a.out}/t001w.csv", ["werks", "name1", "ort01"], PLANTS)
    write(f"{a.out}/mara.csv", ["matnr", "maktx", "mtart", "matkl", "meins", "lvorm"], mara)
    write(f"{a.out}/marc.csv", ["matnr", "werks", "dismm", "dispo", "disls", "bstfe",
                                "plifz", "dzeit", "eisbe", "beskz", "maabc"], marc)
    write(f"{a.out}/mard.csv", ["matnr", "werks", "lgort", "labst", "insme"], mard)
    write(f"{a.out}/mbew.csv", ["matnr", "bwkey", "stprs", "vprsv"], mbew)
    write(f"{a.out}/ekpo.csv", ["ebeln", "ebelp", "matnr", "werks", "lifnr", "menge",
                                "wemng", "eindt", "netpr"], ekpo)
    write(f"{a.out}/plaf.csv", ["plnum", "matnr", "plwrk", "gsmng", "psttr", "pedtr",
                                "paart"], plaf)
    write(f"{a.out}/consumption.csv", ["matnr", "werks", "period", "qty"], consumption)
    write(f"{a.out}/deliveries.csv", ["vbeln", "matnr", "werks", "req_date", "gi_date",
                                      "order_qty", "delivered_qty"], deliveries)
    write(f"{a.out}/_injected_issues.csv", ["rule_id", "matnr", "werks", "doc"], injected)

    print(f"materials={len(mara)} plant_materials={len(marc)} po_lines={len(ekpo)} "
          f"planned_orders={len(plaf)} consumption_rows={len(consumption)} "
          f"deliveries={len(deliveries)} injected_issues={len(injected)}")


if __name__ == "__main__":
    main()
