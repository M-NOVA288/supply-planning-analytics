"""
Static preview of the Power BI report layout, rendered with matplotlib so the
README can show results without Power BI installed. The live report is built
from powerbi/data/ following powerbi/MODEL.md.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]   # categorical slots 1-3 (validated all-pairs)


def _style(ax, title):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold", pad=10)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def render(con, path):
    k = con.execute("""
        SELECT SUM(inventory_value), SUM(excess_value),
               SUM(otif_pct * plant_materials) / SUM(plant_materials),
               SUM(fill_rate_pct * plant_materials) / SUM(plant_materials),
               SUM(forecast_accuracy_pct * plant_materials) / SUM(plant_materials),
               SUM(dq_findings), SUM(shortage_risks + stockouts)
        FROM kpi_plant""").fetchone()
    inv, excess, otif, fill, fa, dq, short = k

    plants = con.execute("SELECT werks || ' ' || plant_name FROM kpi_plant ORDER BY werks").fetchall()
    plants = [p[0] for p in plants]
    status = {}
    for s in ("HEALTHY", "SHORTAGE_RISK", "EXCESS"):
        status[s] = [r[0] for r in con.execute(f"""
            SELECT ROUND(SUM(CASE WHEN m.availability_status = '{s}' THEN m.stock_value ELSE 0 END) / 1e6, 2)
            FROM t001w w LEFT JOIN zc_materialavailability m ON m.werks = w.werks
            GROUP BY w.werks ORDER BY w.werks""")]
    dq_rules = con.execute("""
        SELECT r.rule_id || '  ' || r.rule_name, COUNT(i.rule_id)
        FROM dq_rules r LEFT JOIN mrp_dq_issues i USING (rule_id)
        GROUP BY r.rule_id ORDER BY COUNT(i.rule_id)""").fetchall()
    svc = con.execute("SELECT otif_pct, fill_rate_pct FROM kpi_plant ORDER BY werks").fetchall()

    fig = plt.figure(figsize=(13, 8.2), facecolor=SURFACE)
    fig.suptitle("Supply Planning Analytics  ·  network view as of 2026-10-01",
                 x=0.04, y=0.975, ha="left", fontsize=14, color=INK, fontweight="bold")

    # ---- KPI tiles ----
    tiles = [("Inventory value", f"${inv / 1e6:.1f}M"),
             ("Excess inventory", f"{100 * excess / inv:.0f}%"),
             ("OTIF", f"{otif:.0f}%"),
             ("Fill rate", f"{fill:.1f}%"),
             ("Forecast accuracy", f"{fa:.0f}%"),
             ("Shortage risks", f"{int(short)}"),
             ("MRP data issues", f"{int(dq)}")]
    for i, (label, value) in enumerate(tiles):
        x = 0.04 + i * 0.134
        fig.text(x, 0.885, value, fontsize=20, color=INK, fontweight="bold")
        fig.text(x, 0.86, label, fontsize=9, color=INK_2)

    top = fig.add_gridspec(1, 2, left=0.13, right=0.97, top=0.79, bottom=0.50, wspace=0.42)
    bottom = fig.add_gridspec(1, 1, left=0.36, right=0.95, top=0.38, bottom=0.06)

    # ---- inventory value by plant and availability status (stacked, parts of whole) ----
    ax = fig.add_subplot(top[0, 0])
    _style(ax, "Inventory value by status ($M)")
    left = [0] * len(plants)
    names = {"HEALTHY": "Healthy", "SHORTAGE_RISK": "Shortage risk", "EXCESS": "Excess (>180 days)"}
    for c, s in zip(SERIES, status):
        ax.barh(plants, status[s], left=left, color=c, height=0.55, label=names[s],
                edgecolor=SURFACE, linewidth=2)
        left = [a + b for a, b in zip(left, status[s])]
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left", bbox_to_anchor=(0, -0.12),
              labelcolor=INK_2)

    # ---- service by plant ----
    ax = fig.add_subplot(top[0, 1])
    _style(ax, "Service level by plant (%)")
    y = range(len(plants))
    ax.barh([i - 0.15 for i in y], [s[0] for s in svc], height=0.28, color=SERIES[0], label="OTIF")
    ax.barh([i + 0.15 for i in y], [s[1] for s in svc], height=0.28, color=SERIES[1], label="Fill rate")
    for i, (o, f) in enumerate(svc):
        ax.text(o + 0.6, i - 0.15, f"{o:.0f}", va="center", fontsize=8, color=INK_2)
        ax.text(f + 0.6, i + 0.15, f"{f:.0f}", va="center", fontsize=8, color=INK_2)
    ax.set_yticks(list(y), plants)
    ax.set_xlim(0, 105)
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper left", bbox_to_anchor=(0, -0.12),
              labelcolor=INK_2)

    # ---- MRP data quality findings by rule ----
    ax = fig.add_subplot(bottom[0, 0])
    _style(ax, "MRP data-quality findings by rule")
    labels = [r[0] for r in dq_rules]
    vals = [r[1] for r in dq_rules]
    ax.barh(labels, vals, color=SERIES[0], height=0.6)
    for i, v in enumerate(vals):
        ax.text(v + 0.5, i, str(v), va="center", fontsize=8, color=INK_2)

    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)
