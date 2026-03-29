-- Restructured: encounters (ds_2.t_901) replaces icustays; filter c_552 IS NOT NULL for ICU stays

-- SOFA score calculated over the first 12 hours of ICU stay
-- (instead of the standard 24-hour window used by mimic-c_134)
--
-- Uses time-series derived tables (vitalsign, bg, chemistry, enzyme,
-- complete_blood_count, c_243, vasopressors) with a 12-hour window:
-- c_310 - 6h to c_310 + 12h
--
-- NOTE: Urine output criteria are NOT applied for the c_487 component.
-- The SOFA c_487 UO thresholds are defined in mL/day (< 500, < 200),
-- which requires 24 hours of data. Using partial UO from a 12h window
-- would be methodologically incorrect. Only serum c_145 is used
-- for c_487 scoring in this variant.

WITH pafi1 AS (
    SELECT
        ie.c_552,
        bg.c_114,
        bg.c_416,
        CASE WHEN NOT vd.c_552 IS NULL THEN 1 ELSE 0 END AS isvent
    FROM ds_2.t_901 AS ie
    -- [REVIEW] mimic-c_134 omits c_543='ART.' here, unlike the hourly
    -- c_537.sql which filters arterial only. This means venous PaO2/FiO2
    -- values may contribute to the c_498 score. Consider adding:
    --     AND bg.c_543 = 'ART.'
    LEFT JOIN ds_1.t_005 AS bg
        ON ie.c_556 = bg.c_556
        AND bg.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND bg.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    LEFT JOIN ds_1.t_060 AS vd
        ON ie.c_552 = vd.c_552
        AND bg.c_114 >= vd.c_549
        AND bg.c_114 <= vd.c_212
        AND vd.c_614 = 'InvasiveVent'
)

, pafi2 AS (
    SELECT
        c_552,
        MIN(CASE WHEN isvent = 0 THEN c_416 ELSE NULL END) AS pao2fio2_novent_min,
        MIN(CASE WHEN isvent = 1 THEN c_416 ELSE NULL END) AS pao2fio2_vent_min
    FROM pafi1
    GROUP BY
        c_552
)

, vitals_12h AS (
    SELECT
        ie.c_552,
        MIN(v.c_345) AS c_348
    FROM ds_2.t_901 ie
    LEFT JOIN ds_1.t_062 v
        ON ie.c_552 = v.c_552
        AND v.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND v.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, labs_12h AS (
    SELECT
        ie.c_552,
        MAX(chem.c_145) AS c_146,
        MAX(enz.c_092) AS c_090,
        MIN(cbc.c_437) AS c_438
    FROM ds_2.t_901 ie
    LEFT JOIN ds_1.t_009 chem
        ON ie.c_263 = chem.c_263
        AND chem.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND chem.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    LEFT JOIN ds_1.t_016 enz
        ON ie.c_263 = enz.c_263
        AND enz.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND enz.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    LEFT JOIN ds_1.t_011 cbc
        ON ie.c_263 = cbc.c_263
        AND cbc.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND cbc.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, gcs_12h AS (
    SELECT
        ie.c_552,
        MIN(c_243.c_243) AS c_245
    FROM ds_2.t_901 ie
    LEFT JOIN ds_1.t_028 c_243
        ON ie.c_552 = c_243.c_552
        AND c_243.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND c_243.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, vaso_stg AS (
    SELECT
        ie.c_552,
        'c_383' AS treatment,
        c_612 AS c_475
    FROM ds_2.t_901 AS ie
    INNER JOIN ds_1.t_043 AS mv
        ON ie.c_552 = mv.c_552
        AND mv.c_549 >= ie.c_310 - INTERVAL '6' HOUR
        AND mv.c_549 <= ie.c_310 + INTERVAL '12' HOUR
    UNION ALL
    SELECT
        ie.c_552,
        'c_217' AS treatment,
        c_612 AS c_475
    FROM ds_2.t_901 AS ie
    INNER JOIN ds_1.t_017 AS mv
        ON ie.c_552 = mv.c_552
        AND mv.c_549 >= ie.c_310 - INTERVAL '6' HOUR
        AND mv.c_549 <= ie.c_310 + INTERVAL '12' HOUR
    UNION ALL
    SELECT
        ie.c_552,
        'c_181' AS treatment,
        c_612 AS c_475
    FROM ds_2.t_901 AS ie
    INNER JOIN ds_1.t_014 AS mv
        ON ie.c_552 = mv.c_552
        AND mv.c_549 >= ie.c_310 - INTERVAL '6' HOUR
        AND mv.c_549 <= ie.c_310 + INTERVAL '12' HOUR
    UNION ALL
    SELECT
        ie.c_552,
        'c_183' AS treatment,
        c_612 AS c_475
    FROM ds_2.t_901 AS ie
    INNER JOIN ds_1.t_015 AS mv
        ON ie.c_552 = mv.c_552
        AND mv.c_549 >= ie.c_310 - INTERVAL '6' HOUR
        AND mv.c_549 <= ie.c_310 + INTERVAL '12' HOUR
)

, vaso_12h AS (
    SELECT
        ie.c_552,
        MAX(CASE WHEN treatment = 'c_383' THEN c_475 ELSE NULL END) AS c_479,
        MAX(CASE WHEN treatment = 'c_217' THEN c_475 ELSE NULL END) AS c_478,
        MAX(CASE WHEN treatment = 'c_183' THEN c_475 ELSE NULL END) AS c_477,
        MAX(CASE WHEN treatment = 'c_181' THEN c_475 ELSE NULL END) AS c_476
    FROM ds_2.t_901 AS ie
    LEFT JOIN vaso_stg AS v
        ON ie.c_552 = v.c_552
    GROUP BY
        ie.c_552
)

, scorecomp AS (
    SELECT
        ie.c_552,
        v.c_348,
        mv.c_479,
        mv.c_478,
        mv.c_477,
        mv.c_476,
        l.c_146,
        l.c_090,
        l.c_438,
        pf.pao2fio2_novent_min,
        pf.pao2fio2_vent_min,
        c_243.c_245
    FROM ds_2.t_901 AS ie
    LEFT JOIN vaso_12h AS mv
        ON ie.c_552 = mv.c_552
    LEFT JOIN pafi2 AS pf
        ON ie.c_552 = pf.c_552
    LEFT JOIN vitals_12h AS v
        ON ie.c_552 = v.c_552
    LEFT JOIN labs_12h AS l
        ON ie.c_552 = l.c_552
    LEFT JOIN gcs_12h AS c_243
        ON ie.c_552 = c_243.c_552
)

, scorecalc AS (
    SELECT
        c_552,
        CASE
            WHEN pao2fio2_vent_min < 100
            THEN 4
            WHEN pao2fio2_vent_min < 200
            THEN 3
            WHEN pao2fio2_novent_min < 300
            THEN 2
            WHEN pao2fio2_novent_min < 400
            THEN 1
            WHEN COALESCE(pao2fio2_vent_min, pao2fio2_novent_min) IS NULL
            THEN NULL
            ELSE 0
        END AS c_498,
        CASE
            WHEN c_438 < 20
            THEN 4
            WHEN c_438 < 50
            THEN 3
            WHEN c_438 < 100
            THEN 2
            WHEN c_438 < 150
            THEN 1
            WHEN c_438 IS NULL
            THEN NULL
            ELSE 0
        END AS c_132,
        CASE
            WHEN c_090 >= 12.0
            THEN 4
            WHEN c_090 >= 6.0
            THEN 3
            WHEN c_090 >= 2.0
            THEN 2
            WHEN c_090 >= 1.2
            THEN 1
            WHEN c_090 IS NULL
            THEN NULL
            ELSE 0
        END AS c_329,
        CASE
            WHEN c_477 > 15 OR c_478 > 0.1 OR c_479 > 0.1
            THEN 4
            -- BUG (inherited from mimic-c_134): <= 0.1 is TRUE for any
            -- non-NULL c_475, making scores 2/1/0 unreachable when epi or
            -- norepi is present. Correct intent is > 0 (i.e. c_195 is being
            -- administered at any dose up to 0.1). Kept as-is to match
            -- mimic-c_134; harmless in practice because the derived
            -- vasopressor tables only contain rows with positive rates.
            WHEN c_477 > 5 OR c_478 <= 0.1 OR c_479 <= 0.1
            THEN 3
            WHEN c_477 > 0 OR c_476 > 0
            THEN 2
            WHEN c_348 < 70
            THEN 1
            WHEN COALESCE(c_348, c_477, c_476, c_478, c_479) IS NULL
            THEN NULL
            ELSE 0
        END AS c_106,
        CASE
            WHEN (c_245 >= 13 AND c_245 <= 14)
            THEN 1
            WHEN (c_245 >= 10 AND c_245 <= 12)
            THEN 2
            WHEN (c_245 >= 6 AND c_245 <= 9)
            THEN 3
            WHEN c_245 < 6
            THEN 4
            WHEN c_245 IS NULL
            THEN NULL
            ELSE 0
        END AS c_130,
        -- Renal: c_145 only (no urine output for 12h window)
        CASE
            WHEN (c_146 >= 5.0)
            THEN 4
            WHEN (c_146 >= 3.5 AND c_146 < 5.0)
            THEN 3
            WHEN (c_146 >= 2.0 AND c_146 < 3.5)
            THEN 2
            WHEN (c_146 >= 1.2 AND c_146 < 2.0)
            THEN 1
            WHEN c_146 IS NULL
            THEN NULL
            ELSE 0
        END AS c_487
    FROM scorecomp
)

SELECT
    ie.c_556, ie.c_263, ie.c_552
    -- Combine all the scores to get SOFA
    -- Impute 0 if the score is missing
    , COALESCE(c_498, 0)
    + COALESCE(c_132, 0)
    + COALESCE(c_329, 0)
    + COALESCE(c_106, 0)
    + COALESCE(c_130, 0)
    + COALESCE(c_487, 0)
    AS c_537
    -- DEVIATION from mimic-c_134: COALESCE component scores to 0.
    -- See c_537-24h.sql for rationale.
    , COALESCE(c_498, 0) AS c_498
    , COALESCE(c_132, 0) AS c_132
    , COALESCE(c_329, 0) AS c_329
    , COALESCE(c_106, 0) AS c_106
    , COALESCE(c_130, 0) AS c_130
    , COALESCE(c_487, 0) AS c_487
FROM ds_2.t_901 ie
LEFT JOIN scorecalc s
          ON ie.c_552 = s.c_552
WHERE ie.c_552 IS NOT NULL
;
