-- ------------------------------------------------------------------
-- Title: KDIGO Acute Kidney Injury (AKI) staging
-- This query extracts the maximum KDIGO AKI stage for each ICU stay
-- within the first 48 hours of admission. KDIGO stages range 0-3
-- based on creatinine changes, urine output rates, and CRRT.
-- ------------------------------------------------------------------

-- Reference for KDIGO:
--    Kidney Disease: Improving Global Outcomes (KDIGO) Acute Kidney
--    Injury Work Group. "KDIGO Clinical Practice Guideline for Acute
--    Kidney Injury." Kidney Int Suppl. 2012;2:1-138.

-- Aggregates the time-series kdigo_stages table to one row per ICU stay.
-- Takes the maximum stage across all measurement times within 48h.

SELECT
    ie.subject_id, ie.hadm_id, ie.stay_id
    , COALESCE(MAX(k.aki_stage), 0) AS aki_stage
    , COALESCE(MAX(k.aki_stage_creat), 0) AS aki_stage_creat
    , COALESCE(MAX(k.aki_stage_uo), 0) AS aki_stage_uo
    , COALESCE(MAX(CASE WHEN k.aki_stage_crrt > 0 THEN 3 ELSE 0 END), 0) AS aki_stage_crrt
FROM mimiciv_icu.icustays ie
LEFT JOIN mimiciv_derived.kdigo_stages k
    ON ie.stay_id = k.stay_id
    AND k.charttime >= ie.intime
    AND k.charttime <= ie.intime + INTERVAL '48' HOUR
GROUP BY ie.subject_id, ie.hadm_id, ie.stay_id
;
