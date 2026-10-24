-- =============================================================================
-- 01_tables.sql
-- Source tables, named after their SAP S/4HANA counterparts (synthetic data).
-- See docs/data_dictionary.md for every field and its SAP meaning.
-- =============================================================================

CREATE TABLE t001w (            -- plants
    werks   CHAR(4) PRIMARY KEY,
    name1   VARCHAR(30),
    ort01   VARCHAR(30)
);

CREATE TABLE mara (             -- general material data
    matnr   VARCHAR(18) PRIMARY KEY,
    maktx   VARCHAR(40),        -- description (MAKT in S/4)
    mtart   VARCHAR(4),         -- material type: FERT finished, HALB semi, ROH raw
    matkl   VARCHAR(9),         -- material group
    meins   VARCHAR(3),         -- base unit
    lvorm   CHAR(1)             -- 'X' = flagged for deletion
);

CREATE TABLE marc (             -- plant-level MRP settings
    matnr   VARCHAR(18),
    werks   CHAR(4),
    dismm   VARCHAR(2),         -- MRP type: PD = MRP, ND = no planning
    dispo   VARCHAR(3),         -- MRP controller
    disls   VARCHAR(2),         -- lot size: EX lot-for-lot, FX fixed, HB replenish to max
    bstfe   INTEGER,            -- fixed lot size
    plifz   INTEGER,            -- planned delivery time, days (purchased)
    dzeit   INTEGER,            -- in-house production time, days
    eisbe   INTEGER,            -- safety stock
    beskz   CHAR(1),            -- procurement type: F external, E in-house
    maabc   CHAR(1),            -- ABC indicator
    PRIMARY KEY (matnr, werks)
);

CREATE TABLE mard (             -- storage location stock
    matnr   VARCHAR(18),
    werks   CHAR(4),
    lgort   CHAR(4),
    labst   INTEGER,            -- unrestricted stock
    insme   INTEGER,            -- quality inspection stock
    PRIMARY KEY (matnr, werks, lgort)
);

CREATE TABLE mbew (             -- valuation
    matnr   VARCHAR(18),
    bwkey   CHAR(4),            -- valuation area = plant
    stprs   DECIMAL(11,2),      -- standard price
    vprsv   CHAR(1),            -- price control: S standard
    PRIMARY KEY (matnr, bwkey)
);

CREATE TABLE ekpo (             -- purchase order items with schedule line (EKPO + EKET)
    ebeln   INTEGER,
    ebelp   INTEGER,
    matnr   VARCHAR(18),
    werks   CHAR(4),
    lifnr   VARCHAR(10),        -- vendor
    menge   INTEGER,            -- ordered quantity
    wemng   INTEGER,            -- goods received quantity
    eindt   DATE,               -- delivery date (EKET)
    netpr   DECIMAL(11,2),
    PRIMARY KEY (ebeln, ebelp)
);

CREATE TABLE plaf (             -- planned orders from the MRP run
    plnum   INTEGER PRIMARY KEY,
    matnr   VARCHAR(18),
    plwrk   CHAR(4),
    gsmng   INTEGER,            -- planned quantity
    psttr   DATE,               -- planned start / order date
    pedtr   DATE,               -- planned finish / availability date
    paart   VARCHAR(4)          -- NB purchase requisition, LA production
);

CREATE TABLE consumption (      -- monthly goods issues (MVER-style history)
    matnr   VARCHAR(18),
    werks   CHAR(4),
    period  DATE,
    qty     INTEGER,
    PRIMARY KEY (matnr, werks, period)
);

CREATE TABLE deliveries (       -- outbound deliveries, last 90 days (LIKP/LIPS)
    vbeln         INTEGER PRIMARY KEY,
    matnr         VARCHAR(18),
    werks         CHAR(4),
    req_date      DATE,         -- customer requested date
    gi_date       DATE,         -- actual goods issue
    order_qty     INTEGER,
    delivered_qty INTEGER
);

-- written by python/forecast.py
CREATE TABLE forecast (
    matnr   VARCHAR(18),
    werks   CHAR(4),
    period  DATE,
    qty     REAL,
    method  VARCHAR(20),
    PRIMARY KEY (matnr, werks, period)
);

CREATE TABLE forecast_accuracy (
    matnr          VARCHAR(18),
    werks          CHAR(4),
    method         VARCHAR(20),
    backtest_wape  REAL,        -- weighted absolute % error over the 6-month holdout
    naive_wape     REAL,        -- same, for the last-value benchmark
    PRIMARY KEY (matnr, werks)
);

CREATE TABLE run_params (as_of_date DATE, horizon_days INTEGER, excess_days INTEGER);
