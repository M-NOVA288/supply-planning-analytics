-- =============================================================================
-- 04_kpis.sql
-- Plant KPI scorecard for planning, operations and leadership:
-- inventory value and health, service (OTIF, fill rate), supply reliability,
-- MRP data quality and forecast accuracy.
-- =============================================================================

DROP TABLE IF EXISTS kpi_plant;
CREATE TABLE kpi_plant AS
WITH inv AS (
    SELECT werks,
           COUNT(*)                                                         AS plant_materials,
           ROUND(SUM(stock_value), 0)                                       AS inventory_value,
           ROUND(SUM(CASE WHEN availability_status = 'EXCESS' THEN stock_value ELSE 0 END), 0) AS excess_value,
           SUM(availability_status = 'STOCKOUT')                            AS stockouts,
           SUM(availability_status = 'SHORTAGE_RISK')                       AS shortage_risks,
           ROUND(SUM(CASE WHEN demand_daily > 0 THEN stock_value END)
                 / NULLIF(SUM(CASE WHEN demand_daily > 0 THEN demand_daily * std_price END), 0), 1)
                                                                            AS weighted_days_of_supply
    FROM zc_materialavailability GROUP BY werks
),
svc AS (
    SELECT werks,
           ROUND(100.0 * SUM(gi_date <= req_date AND delivered_qty = order_qty) / COUNT(*), 1) AS otif_pct,
           ROUND(100.0 * SUM(delivered_qty) / SUM(order_qty), 1)                              AS fill_rate_pct
    FROM deliveries GROUP BY werks
),
po AS (
    SELECT werks, ROUND(100.0 * SUM(overdue_po_lines) / NULLIF(SUM(open_po_lines), 0), 1) AS overdue_po_pct
    FROM zi_opensupply GROUP BY werks
),
dq AS (
    SELECT werks, COUNT(*) AS dq_findings, COUNT(DISTINCT matnr) AS dq_materials
    FROM mrp_dq_issues GROUP BY werks
),
fa AS (
    SELECT a.werks,
           ROUND(100.0 - SUM(a.backtest_wape * d.qty_12m) / NULLIF(SUM(d.qty_12m), 0), 1) AS forecast_accuracy_pct
    FROM forecast_accuracy a
    JOIN zi_demandprofile d ON d.matnr = a.matnr AND d.werks = a.werks
    GROUP BY a.werks
)
SELECT w.werks, w.name1 AS plant_name,
       inv.plant_materials, inv.inventory_value, inv.excess_value,
       ROUND(100.0 * inv.excess_value / NULLIF(inv.inventory_value, 0), 1) AS excess_pct,
       inv.weighted_days_of_supply, inv.stockouts, inv.shortage_risks,
       svc.otif_pct, svc.fill_rate_pct, po.overdue_po_pct,
       COALESCE(dq.dq_findings, 0) AS dq_findings,
       ROUND(100.0 * (inv.plant_materials - COALESCE(dq.dq_materials, 0)) / inv.plant_materials, 1)
                                                                 AS dq_clean_pct,
       fa.forecast_accuracy_pct
FROM t001w w
JOIN inv ON inv.werks = w.werks
LEFT JOIN svc ON svc.werks = w.werks
LEFT JOIN po  ON po.werks  = w.werks
LEFT JOIN dq  ON dq.werks  = w.werks
LEFT JOIN fa  ON fa.werks  = w.werks
ORDER BY w.werks;

SELECT * FROM kpi_plant;

-- Planner work list: what to act on first
SELECT werks, matnr, maktx, maabc, availability_status, stock, safety_stock,
       ROUND(demand_daily, 1) AS demand_daily, lead_time_days, po_qty_in_lt,
       projected_stock_end_lt, days_of_supply
FROM zc_materialavailability
WHERE availability_status IN ('STOCKOUT', 'SHORTAGE_RISK')
ORDER BY CASE availability_status WHEN 'STOCKOUT' THEN 0 ELSE 1 END,
         CASE maabc WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
         projected_stock_end_lt - safety_stock
LIMIT 15;
