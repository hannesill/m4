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
    ie.c_556, ie.c_263, ie.c_552
    , COALESCE(MAX(k.c_034), 0) AS c_034
    , COALESCE(MAX(k.c_035), 0) AS c_035
    , COALESCE(MAX(k.c_038), 0) AS c_038
    , COALESCE(MAX(CASE WHEN k.c_036 > 0 THEN 3 ELSE 0 END), 0) AS c_036
FROM ds_3.t_005 ie
LEFT JOIN ds_1.t_037 k
    ON ie.c_552 = k.c_552
    AND k.c_114 >= ie.c_310
    AND k.c_114 <= ie.c_310 + INTERVAL '48' HOUR
GROUP BY ie.c_556, ie.c_263, ie.c_552
;
