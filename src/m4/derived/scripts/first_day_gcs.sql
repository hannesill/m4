-- Derived table: first_day_gcs
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/firstday/first_day_gcs.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts the minimum Glasgow Coma Scale (GCS) recorded
-- during the first 24 hours of ICU admission.
-- Time window: 6 hours before ICU admission to 24 hours after.
--
-- Depends on: mimiciv_derived.gcs

CREATE TABLE IF NOT EXISTS mimiciv_derived.first_day_gcs AS
WITH gcs_final AS (
    SELECT
        ie.subject_id
        , ie.stay_id
        , g.gcs
        , g.gcs_motor
        , g.gcs_verbal
        , g.gcs_eyes
        , g.gcs_unable
        , ROW_NUMBER() OVER (
            PARTITION BY g.stay_id
            ORDER BY g.gcs
        ) AS gcs_seq
    FROM icu_icustays ie
    LEFT JOIN mimiciv_derived.gcs g
        ON ie.stay_id = g.stay_id
            AND g.charttime >= ie.intime - INTERVAL '6' HOUR
            AND g.charttime <= ie.intime + INTERVAL '1' DAY
)

SELECT
    ie.subject_id
    , ie.stay_id
    , gcs AS gcs_min
    , gcs_motor
    , gcs_verbal
    , gcs_eyes
    , gcs_unable
FROM icu_icustays ie
LEFT JOIN gcs_final gs
    ON ie.stay_id = gs.stay_id
        AND gs.gcs_seq = 1
;
