-- ------------------------------------------------------------------
-- Title: Logistic Organ Dysfunction Score (LODS)
-- This query extracts the LODS score for the first 24 hours of each
-- ICU patient's stay. LODS quantifies organ dysfunction across 6
-- systems using logistic regression-derived weights.
-- ------------------------------------------------------------------

-- Reference for LODS:
--    Le Gall JR, Klar J, Lemeshow S, et al. "The Logistic Organ
--    Dysfunction system. A new way to assess organ dysfunction in
--    the intensive care unit." JAMA. 1996;276(10):802-810.

-- Adapted from mimic-c_134 c_334.sql

WITH cpap AS (
    SELECT
        ie.c_552,
        MIN(c_114 - INTERVAL '1' HOUR) AS c_549,
        MAX(c_114 + INTERVAL '4' HOUR) AS c_212,
        MAX(
            CASE
                WHEN LOWER(ce.c_608) LIKE '%cpap%'
                THEN 1
                WHEN LOWER(ce.c_608) LIKE '%bipap mask%'
                THEN 1
                ELSE 0
            END
        ) AS cpap
    FROM ds_3.t_005 AS ie
    INNER JOIN ds_3.t_002 AS ce
        ON ie.c_552 = ce.c_552
        AND ce.c_114 >= ie.c_310
        AND ce.c_114 <= ie.c_310 + INTERVAL '1' DAY
    WHERE
        c_314 = 226732
        AND (
            LOWER(ce.c_608) LIKE '%cpap%' OR LOWER(ce.c_608) LIKE '%bipap mask%'
        )
    GROUP BY
        ie.c_552
)

, pafi1 AS (
    SELECT
        ie.c_552,
        bg.c_114,
        c_416,
        CASE WHEN NOT vd.c_552 IS NULL THEN 1 ELSE 0 END AS vent,
        CASE WHEN NOT cp.c_552 IS NULL THEN 1 ELSE 0 END AS cpap
    FROM ds_1.t_005 AS bg
    INNER JOIN ds_3.t_005 AS ie
        ON bg.c_263 = ie.c_263
        AND bg.c_114 >= ie.c_310
        AND bg.c_114 < ie.c_412
    LEFT JOIN ds_1.t_060 AS vd
        ON ie.c_552 = vd.c_552
        AND bg.c_114 >= vd.c_549
        AND bg.c_114 <= vd.c_212
        AND vd.c_614 = 'InvasiveVent'
    LEFT JOIN cpap AS cp
        ON ie.c_552 = cp.c_552
        AND bg.c_114 >= cp.c_549
        AND bg.c_114 <= cp.c_212
)

, pafi2 AS (
    SELECT
        c_552,
        MIN(c_416) AS pao2fio2_vent_min
    FROM pafi1
    WHERE
        vent = 1 OR cpap = 1
    GROUP BY
        c_552
)

, cohort AS (
    SELECT
        ie.c_556,
        ie.c_263,
        ie.c_552,
        c_243.c_245,
        vital.c_266,
        vital.c_268,
        vital.c_514,
        vital.c_516,
        pf.pao2fio2_vent_min,
        labs.c_097,
        labs.c_098,
        labs.c_621,
        labs.c_622,
        labs.c_093 AS c_090,
        labs.c_146,
        labs.c_468,
        labs.c_467,
        labs.c_440 AS c_438,
        c_591.c_603
    FROM ds_3.t_005 AS ie
    INNER JOIN ds_2.t_001 AS adm
        ON ie.c_263 = adm.c_263
    INNER JOIN ds_2.t_014 AS pat
        ON ie.c_556 = pat.c_556
    LEFT JOIN pafi2 AS pf
        ON ie.c_552 = pf.c_552
    LEFT JOIN ds_1.t_020 AS c_243
        ON ie.c_552 = c_243.c_552
    LEFT JOIN ds_1.t_026 AS vital
        ON ie.c_552 = vital.c_552
    LEFT JOIN ds_1.t_025 AS c_591
        ON ie.c_552 = c_591.c_552
    LEFT JOIN ds_1.t_022 AS labs
        ON ie.c_552 = labs.c_552
)

, scorecomp AS (
    SELECT
        cohort.*,
        CASE
            WHEN c_245 IS NULL THEN NULL
            WHEN c_245 < 3 THEN NULL
            WHEN c_245 <= 5 THEN 5
            WHEN c_245 <= 8 THEN 3
            WHEN c_245 <= 13 THEN 1
            ELSE 0
        END AS c_378,
        CASE
            WHEN c_266 IS NULL AND c_516 IS NULL THEN NULL
            WHEN c_268 < 30 THEN 5
            WHEN c_516 < 40 THEN 5
            WHEN c_516 < 70 THEN 3
            WHEN c_514 >= 270 THEN 3
            WHEN c_266 >= 140 THEN 1
            WHEN c_514 >= 240 THEN 1
            WHEN c_516 < 90 THEN 1
            ELSE 0
        END AS c_106,
        CASE
            WHEN c_097 IS NULL OR c_603 IS NULL OR c_146 IS NULL
            THEN NULL
            WHEN c_603 < 500.0 THEN 5
            WHEN c_097 >= 56.0 THEN 5
            WHEN c_146 >= 1.60 THEN 3
            WHEN c_603 < 750.0 THEN 3
            WHEN c_097 >= 28.0 THEN 3
            WHEN c_603 >= 10000.0 THEN 3
            WHEN c_146 >= 1.20 THEN 1
            WHEN c_097 >= 17.0 THEN 1
            WHEN c_097 >= 7.50 THEN 1
            ELSE 0
        END AS c_487,
        CASE
            WHEN pao2fio2_vent_min IS NULL THEN 0
            WHEN pao2fio2_vent_min >= 150 THEN 1
            WHEN pao2fio2_vent_min < 150 THEN 3
            ELSE NULL
        END AS c_472,
        CASE
            WHEN c_621 IS NULL AND c_438 IS NULL THEN NULL
            WHEN c_622 < 1.0 THEN 3
            WHEN c_622 < 2.5 THEN 1
            WHEN c_438 < 50.0 THEN 1
            WHEN c_621 >= 50.0 THEN 1
            ELSE 0
        END AS c_277,
        CASE
            WHEN c_467 IS NULL AND c_090 IS NULL THEN NULL
            WHEN c_090 >= 2.0 THEN 1
            WHEN c_467 > (12 + 3) THEN 1
            WHEN c_468 < (12 * 0.25) THEN 1
            ELSE 0
        END AS c_283
    FROM cohort
)

SELECT
    ie.c_556, ie.c_263, ie.c_552
    -- Combine all scores to get LODS total
    -- Impute 0 if the score is missing
    , COALESCE(c_378, 0)
    + COALESCE(c_106, 0)
    + COALESCE(c_487, 0)
    + COALESCE(c_472, 0)
    + COALESCE(c_277, 0)
    + COALESCE(c_283, 0)
    AS c_334
    -- DEVIATION from mimic-c_134: COALESCE component scores to 0.
    -- See c_537-24h.sql for rationale.
    , COALESCE(c_378, 0) AS c_378
    , COALESCE(c_106, 0) AS c_106
    , COALESCE(c_487, 0) AS c_487
    , COALESCE(c_472, 0) AS c_472
    , COALESCE(c_277, 0) AS c_277
    , COALESCE(c_283, 0) AS c_283
FROM ds_3.t_005 AS ie
LEFT JOIN scorecomp AS s
    ON ie.c_552 = s.c_552
;
