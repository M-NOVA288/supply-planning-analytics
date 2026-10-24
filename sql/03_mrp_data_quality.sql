-- =============================================================================
-- 03_mrp_data_quality.sql
-- Master-data and transactional checks for problems that make MRP plan wrong:
-- missing lead times, no safety stock on critical parts, broken lot sizes,
-- unplanned materials that still have demand, and stale supply elements.
-- Every finding lands in mrp_dq_issues with a severity and a plain-English
-- detail line a planner can act on. 04_kpis.sql rolls these into a scorecard.
-- =============================================================================

DROP TABLE IF EXISTS dq_rules;
CREATE TABLE dq_rules (rule_id TEXT PRIMARY KEY, rule_name TEXT, severity TEXT, mrp_impact TEXT);
INSERT INTO dq_rules VALUES
 ('DQ01','Purchased part with no planned delivery time','HIGH','MRP schedules receipts with zero lead time, so orders are placed too late'),
 ('DQ02','A-class material with no safety stock','HIGH','No buffer on the highest-value, highest-risk parts'),
 ('DQ03','Fixed lot size procedure with lot size of zero','HIGH','MRP cannot create a valid order quantity'),
 ('DQ04','No MRP controller assigned','MEDIUM','Exception messages reach no planner'),
 ('DQ05','Material set to no planning but still consumed','HIGH','Demand exists that MRP will never cover'),
 ('DQ06','Purchase order past its delivery date','MEDIUM','MRP counts supply that has not arrived'),
 ('DQ07','Planned order past its start date, not converted','MEDIUM','Plan is stale; real order was never released'),
 ('DQ08','Open purchase order on a material flagged for deletion','LOW','Buying stock for a discontinued part');

DROP TABLE IF EXISTS mrp_dq_issues;
CREATE TABLE mrp_dq_issues AS
SELECT 'DQ01' AS rule_id, matnr, werks, '' AS doc,
       'Planned delivery time is 0 days for an externally procured part' AS detail
FROM marc WHERE beskz = 'F' AND COALESCE(plifz, 0) = 0

UNION ALL
SELECT 'DQ02', matnr, werks, '', 'ABC class A with safety stock 0'
FROM marc WHERE maabc = 'A' AND COALESCE(eisbe, 0) = 0

UNION ALL
SELECT 'DQ03', matnr, werks, '', 'Lot size FX but fixed lot size is ' || COALESCE(bstfe, 0)
FROM marc WHERE disls = 'FX' AND COALESCE(bstfe, 0) = 0

UNION ALL
SELECT 'DQ04', matnr, werks, '', 'MRP controller is blank'
FROM marc WHERE COALESCE(TRIM(dispo), '') = ''

UNION ALL
SELECT 'DQ05', c.matnr, c.werks, '', 'MRP type ND but ' || d.qty_12m || ' units consumed in the last 12 months'
FROM marc c JOIN zi_demandprofile d ON d.matnr = c.matnr AND d.werks = c.werks
WHERE c.dismm = 'ND' AND d.qty_12m > 0

UNION ALL
SELECT 'DQ06', e.matnr, e.werks, CAST(e.ebeln AS TEXT),
       'PO ' || e.ebeln || ' due ' || e.eindt || ', ' || (e.menge - e.wemng) || ' units still open ('
       || CAST(julianday(p.as_of_date) - julianday(e.eindt) AS INTEGER) || ' days late)'
FROM ekpo e CROSS JOIN run_params p
WHERE e.eindt < p.as_of_date AND e.menge > e.wemng

UNION ALL
SELECT 'DQ07', l.matnr, l.plwrk, CAST(l.plnum AS TEXT),
       'Planned order ' || l.plnum || ' should have started ' || l.psttr
FROM plaf l CROSS JOIN run_params p
WHERE l.psttr < p.as_of_date

UNION ALL
SELECT 'DQ08', e.matnr, e.werks, CAST(e.ebeln AS TEXT),
       'PO ' || e.ebeln || ' open for ' || (e.menge - e.wemng) || ' units of a deleted material'
FROM ekpo e JOIN mara m ON m.matnr = e.matnr
WHERE m.lvorm = 'X' AND e.menge > e.wemng;

-- findings by rule, for the log
SELECT r.rule_id, r.severity, r.rule_name, COUNT(i.rule_id) AS findings,
       COUNT(DISTINCT i.matnr || '|' || i.werks) AS materials_affected
FROM dq_rules r LEFT JOIN mrp_dq_issues i ON i.rule_id = r.rule_id
GROUP BY r.rule_id, r.severity, r.rule_name
ORDER BY r.rule_id;
