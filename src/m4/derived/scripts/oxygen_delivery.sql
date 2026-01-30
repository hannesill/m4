-- Derived table: oxygen_delivery
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/measurement/oxygen_delivery.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts oxygen delivery information from chartevents,
-- including oxygen flow rates and delivery devices.

CREATE TABLE IF NOT EXISTS mimiciv_derived.oxygen_delivery AS
WITH ce_stg1 AS (
    SELECT
        ce.subject_id
        , ce.stay_id
        , ce.charttime
        -- Consolidate O2 flow itemids (223834 and 227582 → 223834)
        , CASE
            WHEN itemid IN (223834, 227582) THEN 223834
            ELSE itemid END AS itemid
        , value
        , valuenum
        , valueuom
        , storetime
    FROM icu_chartevents ce
    WHERE ce.value IS NOT NULL
        AND ce.itemid IN (
            223834,   -- O2 Flow
            227582,   -- O2 Flow (additional)
            227287    -- O2 Flow (lpm) (additional)
        )
)

, ce_stg2 AS (
    SELECT
        ce.subject_id
        , ce.stay_id
        , ce.charttime
        , itemid
        , value
        , valuenum
        , valueuom
        -- Keep only the most recent value per subject/charttime/itemid
        , ROW_NUMBER() OVER (
            PARTITION BY subject_id, charttime, itemid ORDER BY storetime DESC
        ) AS rn
    FROM ce_stg1 ce
)

, o2 AS (
    -- Oxygen delivery devices
    SELECT
        subject_id
        , stay_id
        , charttime
        , itemid
        , value AS o2_device
        -- Number each device per subject/charttime
        , ROW_NUMBER() OVER (
            PARTITION BY subject_id, charttime, itemid ORDER BY value
        ) AS rn
    FROM icu_chartevents
    WHERE itemid = 226732  -- O2 Delivery Device
)

, stg AS (
    SELECT
        COALESCE(ce.subject_id, o2.subject_id) AS subject_id
        , COALESCE(ce.stay_id, o2.stay_id) AS stay_id
        , COALESCE(ce.charttime, o2.charttime) AS charttime
        , COALESCE(ce.itemid, o2.itemid) AS itemid
        , ce.value
        , ce.valuenum
        , o2.o2_device
        , o2.rn
    FROM ce_stg2 ce
    FULL OUTER JOIN o2
        ON ce.subject_id = o2.subject_id
        AND ce.charttime = o2.charttime
    WHERE ce.rn = 1 OR ce.rn IS NULL
)

SELECT
    subject_id
    , MAX(stay_id) AS stay_id
    , charttime
    , MAX(CASE WHEN itemid = 223834 THEN valuenum ELSE NULL END) AS o2_flow
    , MAX(CASE WHEN itemid = 227287 THEN valuenum ELSE NULL END) AS o2_flow_additional
    -- Support up to 4 concurrent oxygen delivery devices
    , MAX(CASE WHEN rn = 1 THEN o2_device ELSE NULL END) AS o2_delivery_device_1
    , MAX(CASE WHEN rn = 2 THEN o2_device ELSE NULL END) AS o2_delivery_device_2
    , MAX(CASE WHEN rn = 3 THEN o2_device ELSE NULL END) AS o2_delivery_device_3
    , MAX(CASE WHEN rn = 4 THEN o2_device ELSE NULL END) AS o2_delivery_device_4
FROM stg
GROUP BY subject_id, charttime
;
