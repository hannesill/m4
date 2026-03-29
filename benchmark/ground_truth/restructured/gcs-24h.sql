-- Restructured: encounters (ds_2.t_901) replaces icustays; filter c_552 IS NOT NULL for ICU stays

-- ------------------------------------------------------------------
-- Title: Glasgow Coma Scale (GCS) — first day minimum
-- This query extracts the minimum GCS score for the first 24 hours
-- of each ICU stay, along with the component values (motor, verbal,
-- eyes) at the time of the minimum total GCS.
-- ------------------------------------------------------------------

-- Reference for GCS:
--    Teasdale G, Jennett B. "Assessment of coma and impaired
--    consciousness. A practical scale." Lancet. 1974;2(7872):81-84.

-- Adapted from mimic-c_134 first_day_gcs.sql

WITH gcs_final AS (
    SELECT
        ie.c_556,
        ie.c_552,
        g.c_243,
        g.c_246,
        g.c_249,
        g.c_244,
        g.c_248,
        ROW_NUMBER() OVER (PARTITION BY g.c_552 ORDER BY g.c_243 NULLS FIRST) AS gcs_seq
    FROM ds_2.t_901 AS ie
    LEFT JOIN ds_1.t_028 AS g
        ON ie.c_552 = g.c_552
        AND g.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND g.c_114 <= ie.c_310 + INTERVAL '1' DAY
)

SELECT
    ie.c_556, ie.c_263, ie.c_552
    , COALESCE(gs.c_243, 15) AS c_245
    , COALESCE(gs.c_246, 6) AS c_246
    , COALESCE(gs.c_249, 5) AS c_249
    , COALESCE(gs.c_244, 4) AS c_244
FROM ds_2.t_901 AS ie
LEFT JOIN gcs_final AS gs
    ON ie.c_552 = gs.c_552 AND gs.gcs_seq = 1
WHERE ie.c_552 IS NOT NULL
;
