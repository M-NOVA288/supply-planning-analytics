-- =============================================================================
-- 02_planning_views.sql
-- Reporting views in the layered style of S/4HANA CDS views:
--   ZI_ = interface views (reusable building blocks)
--   ZC_ = consumption views (what dashboards and reports read)
-- Written in portable SQL here; docs/cds_mapping.md shows how each one maps to
-- an ABAP CDS view entity and to the released SAP views it would sit on.
-- =============================================================================

DROP VIEW IF EXISTS zi_plantmaterial;
CREATE VIEW zi_plantmaterial AS
SELECT c.matnr, c.werks, w.name1 AS plant_name,
       m.maktx, m.mtart, m.matkl, m.lvorm,
       c.dismm, c.dispo, c.disls, c.bstfe, c.beskz, c.maabc, c.eisbe AS safety_stock,
       CASE WHEN c.beskz = 'E' THEN c.dzeit ELSE c.plifz END AS lead_time_days,
       b.stprs AS std_price
FROM marc c
JOIN mara  m ON m.matnr = c.matnr
JOIN t001w w ON w.werks = c.werks
LEFT JOIN mbew b ON b.matnr = c.matnr AND b.bwkey = c.werks;

DROP VIEW IF EXISTS zi_materialstock;
CREATE VIEW zi_materialstock AS
SELECT matnr, werks, SUM(labst) AS unrestricted, SUM(insme) AS in_inspection
FROM mard
GROUP BY matnr, werks;

DROP VIEW IF EXISTS zi_demandprofile;
CREATE VIEW zi_demandprofile AS
SELECT c.matnr, c.werks,
       ROUND(AVG(CASE WHEN c.period >= date(p.as_of_date, '-3 months')  THEN c.qty END), 1) AS avg_monthly_3m,
       ROUND(AVG(CASE WHEN c.period >= date(p.as_of_date, '-12 months') THEN c.qty END), 1) AS avg_monthly_12m,
       SUM(CASE WHEN c.period >= date(p.as_of_date, '-12 months') THEN c.qty ELSE 0 END)     AS qty_12m
FROM consumption c CROSS JOIN run_params p
GROUP BY c.matnr, c.werks;

DROP VIEW IF EXISTS zi_opensupply;
CREATE VIEW zi_opensupply AS
WITH po AS (
    SELECT e.matnr, e.werks,
           SUM(e.menge - e.wemng)                                          AS open_po_qty,
           SUM(CASE WHEN e.eindt < p.as_of_date THEN e.menge - e.wemng ELSE 0 END) AS overdue_po_qty,
           COUNT(*)                                                        AS open_po_lines,
           SUM(CASE WHEN e.eindt < p.as_of_date THEN 1 ELSE 0 END)         AS overdue_po_lines
    FROM ekpo e CROSS JOIN run_params p
    WHERE e.menge > e.wemng
    GROUP BY e.matnr, e.werks
),
pl AS (
    SELECT matnr, plwrk AS werks, SUM(gsmng) AS planned_order_qty
    FROM plaf GROUP BY matnr, plwrk
)
SELECT pm.matnr, pm.werks,
       COALESCE(po.open_po_qty, 0)      AS open_po_qty,
       COALESCE(po.overdue_po_qty, 0)   AS overdue_po_qty,
       COALESCE(po.open_po_lines, 0)    AS open_po_lines,
       COALESCE(po.overdue_po_lines, 0) AS overdue_po_lines,
       COALESCE(pl.planned_order_qty, 0) AS planned_order_qty
FROM marc pm
LEFT JOIN po ON po.matnr = pm.matnr AND po.werks = pm.werks
LEFT JOIN pl ON pl.matnr = pm.matnr AND pl.werks = pm.werks;

-- supply that lands inside each material's lead time (what can still be counted on)
DROP VIEW IF EXISTS zi_supplywithinleadtime;
CREATE VIEW zi_supplywithinleadtime AS
SELECT pm.matnr, pm.werks,
       COALESCE(SUM(CASE WHEN e.eindt <= date(p.as_of_date, '+' || MAX(pm.lead_time_days, 1) || ' days')
                         THEN e.menge - e.wemng END), 0) AS po_qty_in_lt
FROM zi_plantmaterial pm
CROSS JOIN run_params p
LEFT JOIN ekpo e ON e.matnr = pm.matnr AND e.werks = pm.werks AND e.menge > e.wemng
GROUP BY pm.matnr, pm.werks;

-- -----------------------------------------------------------------------------
-- Consumption view: one row per material/plant with the planner's questions
-- answered. Daily demand uses the forecast when there is one, else the 3-month
-- average. Projected stock = on hand + PO receipts within lead time
-- - forecast demand over the lead time.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS zc_materialavailability;
CREATE VIEW zc_materialavailability AS
WITH f AS (
    SELECT matnr, werks, AVG(qty) AS fcst_monthly
    FROM forecast GROUP BY matnr, werks
),
base AS (
    SELECT pm.*,
           COALESCE(s.unrestricted, 0)                               AS stock,
           COALESCE(d.avg_monthly_3m, 0)                             AS avg_monthly_3m,
           COALESCE(f.fcst_monthly, d.avg_monthly_3m, 0)             AS demand_monthly,
           COALESCE(f.fcst_monthly, d.avg_monthly_3m, 0) / 30.0      AS demand_daily,
           o.open_po_qty, o.overdue_po_qty, o.planned_order_qty,
           lt.po_qty_in_lt
    FROM zi_plantmaterial pm
    LEFT JOIN zi_materialstock s        ON s.matnr = pm.matnr  AND s.werks = pm.werks
    LEFT JOIN zi_demandprofile d        ON d.matnr = pm.matnr  AND d.werks = pm.werks
    LEFT JOIN f                         ON f.matnr = pm.matnr  AND f.werks = pm.werks
    LEFT JOIN zi_opensupply o           ON o.matnr = pm.matnr  AND o.werks = pm.werks
    LEFT JOIN zi_supplywithinleadtime lt ON lt.matnr = pm.matnr AND lt.werks = pm.werks
)
SELECT b.*,
       ROUND(b.stock * b.std_price, 2)                                         AS stock_value,
       CASE WHEN b.demand_daily > 0 THEN ROUND(b.stock / b.demand_daily, 1) END AS days_of_supply,
       ROUND(b.stock + b.po_qty_in_lt
             - b.demand_daily * MAX(b.lead_time_days, 1), 0)                   AS projected_stock_end_lt,
       CASE
         WHEN b.demand_daily = 0                                         THEN 'NO_DEMAND'
         WHEN b.stock = 0                                                THEN 'STOCKOUT'
         WHEN b.stock + b.po_qty_in_lt
              - b.demand_daily * MAX(b.lead_time_days, 1) < b.safety_stock THEN 'SHORTAGE_RISK'
         WHEN b.stock / b.demand_daily > p.excess_days                    THEN 'EXCESS'
         ELSE 'HEALTHY'
       END AS availability_status
FROM base b CROSS JOIN run_params p;
