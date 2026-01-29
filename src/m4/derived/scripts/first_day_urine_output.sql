-- Derived table: first_day_urine_output
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/firstday/first_day_urine_output.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts the total urine output during the first 24 hours
-- of ICU admission.
-- Time window: ICU admission to 24 hours after.
--
-- Depends on: mimiciv_derived.urine_output

CREATE TABLE IF NOT EXISTS mimiciv_derived.first_day_urine_output AS
SELECT
    ie.subject_id
    , ie.stay_id
    , SUM(urineoutput) AS urineoutput
FROM icu_icustays ie
LEFT JOIN mimiciv_derived.urine_output uo
    ON ie.stay_id = uo.stay_id
        AND uo.charttime >= ie.intime
        AND uo.charttime <= ie.intime + INTERVAL '1' DAY
GROUP BY ie.subject_id, ie.stay_id
;
