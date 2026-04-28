-- ------------------------------------------------------------------
-- Title: Oxford Acute Severity of Illness Score (OASIS)
-- This query extracts the OASIS score for the first 24 hours of each
-- ICU patient's stay. OASIS uses 10 components — vitals, urine output,
-- GCS, ventilation status, age, pre-ICU LOS, and admission type.
-- Notably, it requires NO laboratory values.
-- ------------------------------------------------------------------

-- Reference for OASIS:
--    Johnson AEW, Kramer AA, Clifford GD. "A new severity of illness
--    scale using a subset of APACHE data elements shows comparable
--    predictive accuracy." Crit Care Med. 2013;41(7):1711-1718.

-- Adapted from source OASIS implementation

WITH surgflag AS (
    SELECT
        ie.c_552,
        MAX(
            CASE
                WHEN LOWER(c_152) LIKE '%surg%'
                THEN 1
                WHEN c_152 = 'ORTHO'
                THEN 1
                ELSE 0
            END
        ) AS surgical
    FROM ds_3.t_005 AS ie
    LEFT JOIN ds_2.t_021 AS se
        ON ie.c_263 = se.c_263 AND se.c_587 < ie.c_310 + INTERVAL '1' DAY
    GROUP BY
        ie.c_552
)

, vent AS (
    SELECT
        ie.c_552,
        MAX(CASE WHEN NOT v.c_552 IS NULL THEN 1 ELSE 0 END) AS vent
    FROM ds_3.t_005 AS ie
    LEFT JOIN ds_1.t_060 AS v
        ON ie.c_552 = v.c_552
        AND v.c_614 = 'InvasiveVent'
        AND (
            (v.c_549 >= ie.c_310 AND v.c_549 <= ie.c_310 + INTERVAL '1' DAY)
            OR (v.c_212 >= ie.c_310 AND v.c_212 <= ie.c_310 + INTERVAL '1' DAY)
            OR (v.c_549 <= ie.c_310 AND v.c_212 >= ie.c_310 + INTERVAL '1' DAY)
        )
    GROUP BY
        ie.c_552
)

, cohort AS (
    SELECT
        ie.c_556,
        ie.c_263,
        ie.c_552,
        DATE_DIFF('microseconds', adm.c_030, ie.c_310)/60000000.0 AS c_453,
        ag.c_031,
        c_243.c_245,
        vital.c_266,
        vital.c_268,
        vital.c_346,
        vital.c_348,
        vital.c_493,
        vital.c_495,
        vital.c_564,
        vital.c_566,
        vent.vent AS c_357,
        c_591.c_603,
        CASE
            WHEN adm.c_027 = 'ELECTIVE' AND sf.surgical = 1
            THEN 1
            WHEN adm.c_027 IS NULL OR sf.surgical IS NULL
            THEN NULL
            ELSE 0
        END AS c_208
    FROM ds_3.t_005 AS ie
    INNER JOIN ds_2.t_001 AS adm
        ON ie.c_263 = adm.c_263
    INNER JOIN ds_2.t_014 AS pat
        ON ie.c_556 = pat.c_556
    LEFT JOIN ds_1.t_002 AS ag
        ON ie.c_263 = ag.c_263
    LEFT JOIN surgflag AS sf
        ON ie.c_552 = sf.c_552
    LEFT JOIN ds_1.t_020 AS c_243
        ON ie.c_552 = c_243.c_552
    LEFT JOIN ds_1.t_026 AS vital
        ON ie.c_552 = vital.c_552
    LEFT JOIN ds_1.t_025 AS c_591
        ON ie.c_552 = c_591.c_552
    LEFT JOIN vent
        ON ie.c_552 = vent.c_552
)

, scorecomp AS (
    SELECT
        co.c_556,
        co.c_263,
        co.c_552,
        CASE
            WHEN c_453 IS NULL THEN NULL
            WHEN c_453 < 10.2 THEN 5
            WHEN c_453 < 297 THEN 3
            WHEN c_453 < 1440 THEN 0
            WHEN c_453 < 18708 THEN 2
            ELSE 1
        END AS c_454,
        CASE
            WHEN c_031 IS NULL THEN NULL
            WHEN c_031 < 24 THEN 0
            WHEN c_031 <= 53 THEN 3
            WHEN c_031 <= 77 THEN 6
            WHEN c_031 <= 89 THEN 9
            WHEN c_031 >= 90 THEN 7
            ELSE 0
        END AS c_032,
        CASE
            WHEN c_245 IS NULL THEN NULL
            WHEN c_245 <= 7 THEN 10
            WHEN c_245 < 14 THEN 4
            WHEN c_245 = 14 THEN 3
            ELSE 0
        END AS c_247,
        CASE
            WHEN c_266 IS NULL THEN NULL
            WHEN c_266 > 125 THEN 6
            WHEN c_268 < 33 THEN 4
            WHEN c_266 >= 107 AND c_266 <= 125 THEN 3
            WHEN c_266 >= 89 AND c_266 <= 106 THEN 1
            ELSE 0
        END AS c_269,
        CASE
            WHEN c_348 IS NULL THEN NULL
            WHEN c_348 < 20.65 THEN 4
            WHEN c_348 < 51 THEN 3
            WHEN c_346 > 143.44 THEN 3
            WHEN c_348 >= 51 AND c_348 < 61.33 THEN 2
            ELSE 0
        END AS c_350,
        CASE
            WHEN c_495 IS NULL THEN NULL
            WHEN c_495 < 6 THEN 10
            WHEN c_493 > 44 THEN 9
            WHEN c_493 > 30 THEN 6
            WHEN c_493 > 22 THEN 1
            WHEN c_495 < 13 THEN 1
            ELSE 0
        END AS c_496,
        CASE
            WHEN c_564 IS NULL THEN NULL
            WHEN c_564 > 39.88 THEN 6
            WHEN c_566 >= 33.22 AND c_566 <= 35.93 THEN 4
            WHEN c_564 >= 33.22 AND c_564 <= 35.93 THEN 4
            WHEN c_566 < 33.22 THEN 3
            WHEN c_566 > 35.93 AND c_566 <= 36.39 THEN 2
            WHEN c_564 >= 36.89 AND c_564 <= 39.88 THEN 2
            ELSE 0
        END AS c_562,
        CASE
            WHEN c_603 IS NULL THEN NULL
            WHEN c_603 < 671.09 THEN 10
            WHEN c_603 > 6896.80 THEN 8
            WHEN c_603 >= 671.09 AND c_603 <= 1426.99 THEN 5
            WHEN c_603 >= 1427.00 AND c_603 <= 2544.14 THEN 1
            ELSE 0
        END AS c_607,
        CASE
            WHEN c_357 IS NULL THEN NULL
            WHEN c_357 = 1 THEN 9
            ELSE 0
        END AS c_358,
        CASE
            WHEN c_208 IS NULL THEN NULL
            WHEN c_208 = 1 THEN 0
            ELSE 6
        END AS c_209
    FROM cohort AS co
)

SELECT
    c_556, c_263, c_552
    -- Combine all scores to get OASIS total
    -- Impute 0 if the score is missing
    , COALESCE(c_454, 0)
    + COALESCE(c_032, 0)
    + COALESCE(c_247, 0)
    + COALESCE(c_269, 0)
    + COALESCE(c_350, 0)
    + COALESCE(c_496, 0)
    + COALESCE(c_562, 0)
    + COALESCE(c_607, 0)
    + COALESCE(c_358, 0)
    + COALESCE(c_209, 0)
    AS c_396
    -- DEVIATION from source implementation: COALESCE component scores to 0.
    -- See sofa-24h.sql for rationale.
    , COALESCE(c_454, 0) AS c_454
    , COALESCE(c_032, 0) AS c_032
    , COALESCE(c_247, 0) AS c_247
    , COALESCE(c_269, 0) AS c_269
    , COALESCE(c_350, 0) AS c_350
    , COALESCE(c_496, 0) AS c_496
    , COALESCE(c_562, 0) AS c_562
    , COALESCE(c_607, 0) AS c_607
    , COALESCE(c_358, 0) AS c_358
    , COALESCE(c_209, 0) AS c_209
FROM scorecomp
;
