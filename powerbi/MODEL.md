# Power BI model and report

Build the report in Power BI Desktop from the CSVs in `powerbi/data/` (about 15 minutes). The pipeline regenerates them on every run.

## 1. Load the data

**Home → Get data → Text/CSV**, and load each file in `powerbi/data/`. In Power Query, check these types:

| Table | Column | Type |
|---|---|---|
| `fact_demand` | `period` | Date |
| `fact_deliveries` | `req_date`, `gi_date` | Date |
| all tables | `werks` | Text (keeps the leading digits as codes) |
| all tables | `material_plant_key` | Text |

## 2. Relationships (Model view)

A star schema with one shared dimension per grain. All relationships are one-to-many, single direction.

| From (one side) | To (many side) |
|---|---|
| `dim_material_plant[material_plant_key]` | `fact_availability[material_plant_key]` |
| `dim_material_plant[material_plant_key]` | `fact_dq_issues[material_plant_key]` |
| `dim_material_plant[material_plant_key]` | `fact_demand[material_plant_key]` |
| `dim_material_plant[material_plant_key]` | `fact_deliveries[material_plant_key]` |
| `dim_plant[werks]` | `dim_material_plant[werks]` |
| `dim_plant[werks]` | `kpi_plant[werks]` |

Facts also carry `werks` for convenience. Don't relate those columns, or the model becomes ambiguous. Plant filtering flows through `dim_material_plant`.

## 3. Measures

Create an empty `_Measures` table (**Home → Enter data → Load**) and add the measures from [`measures.dax`](measures.dax).

## 4. Report pages

| Page | Visuals |
|---|---|
| **Network overview** | Cards: Inventory Value, Excess %, OTIF %, Fill Rate %, Shortage Risks, DQ Findings. Stacked bar: Inventory Value by plant and `availability_status`. Clustered bar: OTIF % and Fill Rate % by plant. Slicers: plant, ABC class, MRP controller. |
| **Planner work list** | Table from `fact_availability` filtered to `SHORTAGE_RISK` and `STOCKOUT`: material, plant, ABC, stock, safety stock, projected stock at end of lead time, open PO qty. Sorted by ABC, then projected shortfall. |
| **MRP data quality** | Bar: DQ Findings by `rule_name`, colored by severity. Table: rule, material, plant, document, detail. Card: DQ Clean %. |
| **Demand & forecast** | Line: Actual Demand and Forecast Demand by `period`, with a material slicer. Card: Demand Trend 3M vs Prior 3M. |

`docs/dashboard_preview.png` shows the target layout for the overview page.

## Where this goes on a live S/4HANA system

The CSVs stand in for the data an S/4 system exposes through CDS views. On a live system, the same model would connect to those views through SAP's OData services or the Power BI SAP HANA connector, and the measures would carry over unchanged. See `docs/cds_mapping.md`.
