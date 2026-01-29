-- Derived table: gcs
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/measurement/gcs.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts the Glasgow Coma Scale, a measure of neurological function.
--
-- The query has a few special rules:
-- (1) The verbal component can be set to 0 if the patient is ventilated.
--     This is corrected to 5 - the overall GCS is set to 15 in these cases.
-- (2) Often only one of three components is documented. The other components
--     are carried forward.
--
-- ITEMIDs used (METAVISION):
-- 223900 GCS - Verbal Response
-- 223901 GCS - Motor Response
-- 220739 GCS - Eye Opening
--
-- Note:
-- The GCS for sedated patients is defaulted to 15 in this code.
-- This is in line with how the data is meant to be collected.
-- e.g., from the SAPS II publication:
-- For sedated patients, the Glasgow Coma Score before sedation was used.

CREATE TABLE IF NOT EXISTS mimiciv_derived.gcs AS
WITH base AS (
    SELECT
        subject_id
        , ce.stay_id
        , ce.charttime
        , MAX(CASE WHEN ce.itemid = 223901 THEN ce.valuenum ELSE NULL END) AS gcsmotor
        , MAX(CASE
            WHEN ce.itemid = 223900 AND ce.value = 'No Response-ETT' THEN 0
            WHEN ce.itemid = 223900 THEN ce.valuenum
            ELSE NULL
        END) AS gcsverbal
        , MAX(CASE WHEN ce.itemid = 220739 THEN ce.valuenum ELSE NULL END) AS gcseyes
        , MAX(CASE
            WHEN ce.itemid = 223900 AND ce.value = 'No Response-ETT' THEN 1
            ELSE 0
        END) AS endotrachflag
        , ROW_NUMBER() OVER (PARTITION BY ce.stay_id ORDER BY ce.charttime ASC) AS rn
    FROM icu_chartevents ce
    WHERE ce.itemid IN (223900, 223901, 220739)
    GROUP BY ce.subject_id, ce.stay_id, ce.charttime
)

, gcs AS (
    SELECT
        b.*
        , b2.gcsverbal AS gcsverbalprev
        , b2.gcsmotor AS gcsmotorprev
        , b2.gcseyes AS gcseyesprev
        , CASE
            -- replace GCS during sedation with 15
            WHEN b.gcsverbal = 0 THEN 15
            WHEN b.gcsverbal IS NULL AND b2.gcsverbal = 0 THEN 15
            -- if previously intubated but not now, don't use previous values
            WHEN b2.gcsverbal = 0 THEN
                COALESCE(b.gcsmotor, 6) + COALESCE(b.gcsverbal, 5) + COALESCE(b.gcseyes, 4)
            -- otherwise, add up score normally, imputing previous value if none available
            ELSE
                COALESCE(b.gcsmotor, COALESCE(b2.gcsmotor, 6))
                + COALESCE(b.gcsverbal, COALESCE(b2.gcsverbal, 5))
                + COALESCE(b.gcseyes, COALESCE(b2.gcseyes, 4))
        END AS gcs
    FROM base b
    LEFT JOIN base b2
        ON b.stay_id = b2.stay_id
        AND b.rn = b2.rn + 1
        AND b2.charttime > b.charttime - INTERVAL '6' HOUR
)

, gcs_stg AS (
    SELECT
        subject_id
        , gs.stay_id
        , gs.charttime
        , gcs
        , COALESCE(gcsmotor, gcsmotorprev) AS gcsmotor
        , COALESCE(gcsverbal, gcsverbalprev) AS gcsverbal
        , COALESCE(gcseyes, gcseyesprev) AS gcseyes
        , CASE WHEN COALESCE(gcsmotor, gcsmotorprev) IS NULL THEN 0 ELSE 1 END
          + CASE WHEN COALESCE(gcsverbal, gcsverbalprev) IS NULL THEN 0 ELSE 1 END
          + CASE WHEN COALESCE(gcseyes, gcseyesprev) IS NULL THEN 0 ELSE 1 END
          AS components_measured
        , endotrachflag
    FROM gcs gs
)

SELECT
    gs.subject_id
    , gs.stay_id
    , gs.charttime
    , gcs AS gcs
    , gcsmotor AS gcs_motor
    , gcsverbal AS gcs_verbal
    , gcseyes AS gcs_eyes
    , endotrachflag AS gcs_unable
FROM gcs_stg gs
;
