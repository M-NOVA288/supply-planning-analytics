# Data dictionary

All data is synthetic (`scripts/generate_data.py`, seed 7). Tables and fields use SAP names so the SQL reads the way it would on S/4HANA.

| Table | SAP meaning | Grain | Rows |
|---|---|---|---:|
| `t001w` | Plants | plant | 3 |
| `mara` | General material data | material | 150 |
| `marc` | Plant-level MRP settings | material × plant | 327 |
| `mard` | Storage location stock | material × plant × storage location | 327 |
| `mbew` | Material valuation | material × plant | 327 |
| `ekpo` | Purchase order items with delivery date (EKPO + EKET) | PO line | 456 |
| `plaf` | Planned orders from the MRP run | planned order | 346 |
| `consumption` | Monthly goods issues (MVER-style) | material × plant × month, 24 months | 7,848 |
| `deliveries` | Outbound deliveries, last 90 days (LIKP/LIPS) | delivery | 1,537 |

## Key fields

| Field | Table | Meaning | Values |
|---|---|---|---|
| `matnr` | all | Material number | `M100001`… |
| `werks` / `plwrk` / `bwkey` | all | Plant | 1000 Houston DC, 2000 Charlotte Plant, 3000 Rosemont DC |
| `mtart` | MARA | Material type | FERT finished good, HALB semi-finished, ROH raw material |
| `lvorm` | MARA | Deletion flag | `X` = flagged for deletion |
| `dismm` | MARC | MRP type | PD = MRP, ND = no planning |
| `dispo` | MARC | MRP controller | P01–P04 |
| `disls` | MARC | Lot sizing procedure | EX lot-for-lot, FX fixed, HB replenish to maximum |
| `bstfe` | MARC | Fixed lot size | units |
| `plifz` | MARC | Planned delivery time (purchased parts) | days |
| `dzeit` | MARC | In-house production time | days |
| `eisbe` | MARC | Safety stock | units |
| `beskz` | MARC | Procurement type | F external, E in-house |
| `maabc` | MARC | ABC indicator | A, B, C |
| `labst` | MARD | Unrestricted-use stock | units |
| `stprs` | MBEW | Standard price | USD per unit |
| `menge` / `wemng` | EKPO | Ordered / received quantity | units |
| `eindt` | EKET | Delivery date | date |
| `psttr` / `pedtr` | PLAF | Planned order start / finish | date |

## Derived measures

| Measure | Definition |
|---|---|
| Daily demand | Average monthly forecast for the next 3 months ÷ 30 (3-month actual average if no forecast) |
| Days of supply | Unrestricted stock ÷ daily demand |
| Projected stock at end of lead time | Stock + open PO quantity due within the lead time − daily demand × lead time |
| Availability status | STOCKOUT (no stock, demand exists) · SHORTAGE_RISK (projected below safety stock) · EXCESS (more than 180 days of supply) · HEALTHY · NO_DEMAND |
| OTIF | Delivery shipped on or before the requested date **and** in full |
| Fill rate | Delivered quantity ÷ ordered quantity |
| Forecast accuracy | 100 − WAPE on a 6-month holdout, weighted by 12-month volume |
| DQ clean % | Share of material-plant records with no MRP data-quality finding |

## Injected data problems

The generator plants MRP master-data problems on purpose and records each one in `data/_injected_issues.csv`. The test suite checks that every one of them is caught.
