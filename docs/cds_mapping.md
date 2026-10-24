# From this repo to S/4HANA CDS views

The SQL views here follow the layering S/4HANA uses for embedded analytics. **Interface views** (`ZI_`) are reusable building blocks over the base tables. **Consumption views** (`ZC_`) answer the planner's question and are what SAP Analytics Cloud, Fiori analytical apps, or Power BI read.

| This repo | Built on (SAP tables) | Role | In S/4HANA |
|---|---|---|---|
| `zi_plantmaterial` | MARC, MARA, MBEW, T001W | MRP settings, lead time, safety stock, standard price per material and plant | Custom interface view over the released product, plant and valuation views |
| `zi_materialstock` | MARD | Unrestricted and inspection stock | Released material stock view (aggregated from MATDOC in S/4) |
| `zi_demandprofile` | consumption history (MVER) | 3- and 12-month average demand | Custom view over goods-issue history |
| `zi_opensupply` | EKPO / EKET, PLAF | Open and overdue PO quantity, planned orders | Released purchase order item and schedule line views, planned order view |
| `zi_supplywithinleadtime` | EKPO / EKET + lead time | Receipts that land before the lead time runs out | Custom interface view |
| `zc_materialavailability` | all of the above + forecast | Days of supply, projected stock at end of lead time, availability status | Consumption view, annotated as an analytical query |
| `mrp_dq_issues` | MARC, MARA, EKPO, PLAF | MRP master-data and stale-supply findings | Consumption view or scheduled data-quality job |

Exact released view names vary by S/4HANA release. Check the **View Browser** Fiori app or the SAP Business Accelerator Hub (api.sap.com) for the views available on a given system.

Two S/4-specific notes:
- **Stock:** S/4HANA records stock movements in MATDOC. MARD-style stock is a compatibility view over it, so production reporting reads stock through the released stock views rather than MARD directly.
- **Units:** CDS view entities require quantity fields to reference their unit of measure (`@Semantics.quantity.unitOfMeasure`). The flat SQL here assumes everything is in the base unit, EA.

## Example: the plant-material interface view as an ABAP CDS view entity

A sketch of how `zi_plantmaterial` would be written in ABAP CDS. It's included to show the pattern; it hasn't been activated on an SAP system.

```abap
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'Plant material MRP settings'
define view entity ZI_PlantMaterial
  as select from marc
    inner join   mara on mara.matnr = marc.matnr
{
  key marc.matnr as Material,
  key marc.werks as Plant,
      mara.mtart as MaterialType,
      mara.matkl as MaterialGroup,
      mara.lvorm as FlaggedForDeletion,
      marc.dismm as MRPType,
      marc.dispo as MRPController,
      marc.disls as LotSizingProcedure,
      marc.beskz as ProcurementType,
      marc.plifz as PlannedDeliveryDays,
      marc.dzeit as InHouseProductionDays,
      marc.maabc as ABCIndicator
}
```
