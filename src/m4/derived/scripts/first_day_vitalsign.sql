-- Derived table: first_day_vitalsign
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/firstday/first_day_vitalsign.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts vital sign measurements during the first 24 hours
-- of ICU admission, computing min/max/mean for each measure.
-- Time window: 6 hours before ICU admission to 24 hours after.
--
-- Depends on: mimiciv_derived.vitalsign

CREATE TABLE IF NOT EXISTS mimiciv_derived.first_day_vitalsign AS
SELECT
    ie.subject_id
    , ie.stay_id
    -- Heart rate
    , MIN(heart_rate) AS heart_rate_min
    , MAX(heart_rate) AS heart_rate_max
    , AVG(heart_rate) AS heart_rate_mean
    -- Systolic blood pressure
    , MIN(sbp) AS sbp_min
    , MAX(sbp) AS sbp_max
    , AVG(sbp) AS sbp_mean
    -- Diastolic blood pressure
    , MIN(dbp) AS dbp_min
    , MAX(dbp) AS dbp_max
    , AVG(dbp) AS dbp_mean
    -- Mean blood pressure
    , MIN(mbp) AS mbp_min
    , MAX(mbp) AS mbp_max
    , AVG(mbp) AS mbp_mean
    -- Respiratory rate
    , MIN(resp_rate) AS resp_rate_min
    , MAX(resp_rate) AS resp_rate_max
    , AVG(resp_rate) AS resp_rate_mean
    -- Temperature
    , MIN(temperature) AS temperature_min
    , MAX(temperature) AS temperature_max
    , AVG(temperature) AS temperature_mean
    -- Oxygen saturation (SpO2)
    , MIN(spo2) AS spo2_min
    , MAX(spo2) AS spo2_max
    , AVG(spo2) AS spo2_mean
    -- Glucose
    , MIN(glucose) AS glucose_min
    , MAX(glucose) AS glucose_max
    , AVG(glucose) AS glucose_mean
FROM icu_icustays ie
LEFT JOIN mimiciv_derived.vitalsign ce
    ON ie.stay_id = ce.stay_id
        AND ce.charttime >= ie.intime - INTERVAL '6' HOUR
        AND ce.charttime <= ie.intime + INTERVAL '1' DAY
GROUP BY ie.subject_id, ie.stay_id
;
