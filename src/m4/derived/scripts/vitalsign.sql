-- Derived table: vitalsign
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/measurement/vitalsign.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query extracts vital sign measurements from chartevents.
-- Vital signs include: heart rate, blood pressure, respiratory rate,
-- temperature, SpO2, and glucose.

CREATE TABLE IF NOT EXISTS mimiciv_derived.vitalsign AS
SELECT
    ce.subject_id
    , ce.stay_id
    , ce.charttime
    -- Heart rate
    , AVG(CASE WHEN itemid IN (220045)
            AND valuenum > 0
            AND valuenum < 300
            THEN valuenum END
    ) AS heart_rate
    -- Systolic blood pressure
    , AVG(CASE WHEN itemid IN (220179, 220050, 225309)
            AND valuenum > 0
            AND valuenum < 400
            THEN valuenum END
    ) AS sbp
    -- Diastolic blood pressure
    , AVG(CASE WHEN itemid IN (220180, 220051, 225310)
            AND valuenum > 0
            AND valuenum < 300
            THEN valuenum END
    ) AS dbp
    -- Mean blood pressure
    , AVG(CASE WHEN itemid IN (220052, 220181, 225312)
            AND valuenum > 0
            AND valuenum < 300
            THEN valuenum END
    ) AS mbp
    -- Non-invasive systolic blood pressure
    , AVG(CASE WHEN itemid = 220179
            AND valuenum > 0
            AND valuenum < 400
            THEN valuenum END
    ) AS sbp_ni
    -- Non-invasive diastolic blood pressure
    , AVG(CASE WHEN itemid = 220180
            AND valuenum > 0
            AND valuenum < 300
            THEN valuenum END
    ) AS dbp_ni
    -- Non-invasive mean blood pressure
    , AVG(CASE WHEN itemid = 220181
            AND valuenum > 0
            AND valuenum < 300
            THEN valuenum END
    ) AS mbp_ni
    -- Respiratory rate
    , AVG(CASE WHEN itemid IN (220210, 224690)
            AND valuenum > 0
            AND valuenum < 70
            THEN valuenum END
    ) AS resp_rate
    -- Temperature (Fahrenheit converted to Celsius)
    , ROUND(CAST(
            AVG(CASE
                WHEN itemid IN (223761)
                    AND valuenum > 70
                    AND valuenum < 120
                    THEN (valuenum - 32) / 1.8
                WHEN itemid IN (223762)
                    AND valuenum > 10
                    AND valuenum < 50
                    THEN valuenum END)
            AS NUMERIC), 2) AS temperature
    -- Temperature measurement site
    , MAX(CASE WHEN itemid = 224642 THEN value END
    ) AS temperature_site
    -- Oxygen saturation (SpO2)
    , AVG(CASE WHEN itemid IN (220277)
            AND valuenum > 0
            AND valuenum <= 100
            THEN valuenum END
    ) AS spo2
    -- Glucose
    , AVG(CASE WHEN itemid IN (225664, 220621, 226537)
            AND valuenum > 0
            THEN valuenum END
    ) AS glucose
FROM icu_chartevents ce
WHERE ce.stay_id IS NOT NULL
    AND ce.itemid IN
    (
        220045,   -- Heart Rate
        225309,   -- ART BP Systolic
        225310,   -- ART BP Diastolic
        225312,   -- ART BP Mean
        220050,   -- Arterial Blood Pressure systolic
        220051,   -- Arterial Blood Pressure diastolic
        220052,   -- Arterial Blood Pressure mean
        220179,   -- Non Invasive Blood Pressure systolic
        220180,   -- Non Invasive Blood Pressure diastolic
        220181,   -- Non Invasive Blood Pressure mean
        220210,   -- Respiratory Rate
        224690,   -- Respiratory Rate (Total)
        220277,   -- O2 saturation pulseoxymetry
        225664,   -- Glucose finger stick
        220621,   -- Glucose (serum)
        226537,   -- Glucose (whole blood)
        223762,   -- Temperature Celsius
        223761,   -- Temperature Fahrenheit
        224642    -- Temperature Site
    )
GROUP BY ce.subject_id, ce.stay_id, ce.charttime
;
