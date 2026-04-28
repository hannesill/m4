-- SIRS criteria calculated over the first 12 hours of ICU stay
-- (instead of the standard 24-hour source window)
--
-- Uses time-series derived tables (vitalsign, bg, complete_blood_count)
-- with a 12-hour window: intime - 6h to intime + 12h

WITH vitals_12h AS (
    SELECT
        ie.c_552,
        MIN(v.c_563) AS c_566,
        MAX(v.c_563) AS c_564,
        MAX(v.c_265) AS c_266,
        MAX(v.c_492) AS c_493
    FROM ds_3.t_005 ie
    LEFT JOIN ds_1.t_062 v
        ON ie.c_552 = v.c_552
        AND v.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND v.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, bg_art_12h AS (
    SELECT
        ie.c_552,
        MIN(bg.c_425) AS paco2_min
    FROM ds_3.t_005 ie
    LEFT JOIN ds_1.t_005 bg
        ON ie.c_556 = bg.c_556
        AND bg.c_543 = 'ART.'
        AND bg.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND bg.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, labs_12h AS (
    SELECT
        ie.c_552,
        MIN(cbc.c_620) AS c_622,
        MAX(cbc.c_620) AS c_621
    FROM ds_3.t_005 ie
    LEFT JOIN ds_1.t_011 cbc
        ON cbc.c_556 = ie.c_556
        AND cbc.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND cbc.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, bands_12h AS (
    SELECT
        ie.c_552,
        MAX(bd.c_070) AS c_071
    FROM ds_3.t_005 ie
    LEFT JOIN ds_1.t_006 bd
        ON bd.c_556 = ie.c_556
        AND bd.c_114 >= ie.c_310 - INTERVAL '6' HOUR
        AND bd.c_114 <= ie.c_310 + INTERVAL '12' HOUR
    GROUP BY ie.c_552
)

, scorecomp AS (
    SELECT
        ie.c_552,
        v.c_566,
        v.c_564,
        v.c_266,
        v.c_493,
        bg.paco2_min,
        l.c_622,
        l.c_621,
        b.c_071
    FROM ds_3.t_005 ie
    LEFT JOIN vitals_12h v ON ie.c_552 = v.c_552
    LEFT JOIN bg_art_12h bg ON ie.c_552 = bg.c_552
    LEFT JOIN labs_12h l ON ie.c_552 = l.c_552
    LEFT JOIN bands_12h b ON ie.c_552 = b.c_552
)

, scorecalc AS (
    SELECT c_552

        , CASE
            WHEN c_566 < 36.0 THEN 1
            WHEN c_564 > 38.0 THEN 1
            WHEN c_566 IS NULL THEN null
            ELSE 0
        END AS c_562

        , CASE
            WHEN c_266 > 90.0 THEN 1
            WHEN c_266 IS NULL THEN null
            ELSE 0
        END AS c_269

        , CASE
            WHEN c_493 > 20.0 THEN 1
            WHEN paco2_min < 32.0 THEN 1
            WHEN COALESCE(c_493, paco2_min) IS NULL THEN null
            ELSE 0
        END AS c_497

        , CASE
            WHEN c_622 < 4.0 THEN 1
            WHEN c_621 > 12.0 THEN 1
            WHEN c_071 > 10 THEN 1
            WHEN COALESCE(c_622, c_071) IS NULL THEN null
            ELSE 0
        END AS c_623

    FROM scorecomp
)

SELECT
    ie.c_556, ie.c_263, ie.c_552
    , COALESCE(c_562, 0)
    + COALESCE(c_269, 0)
    + COALESCE(c_497, 0)
    + COALESCE(c_623, 0)
    AS c_527
    -- DEVIATION from source implementation: COALESCE component scores to 0.
    -- The original SQL leaves them NULL when underlying data is missing.
    -- We impute 0 here so the ground truth matches the task instruction
    -- ("treat missing data as normal, score 0") and agents are not
    -- penalised for following the instruction. The NULL→0 semantics are
    -- already applied to the SIRS total above; this extends it to the
    -- individual components for consistency.
    , COALESCE(c_562, 0) AS c_562
    , COALESCE(c_269, 0) AS c_269
    , COALESCE(c_497, 0) AS c_497
    , COALESCE(c_623, 0) AS c_623
FROM ds_3.t_005 ie
LEFT JOIN scorecalc s
          ON ie.c_552 = s.c_552
;
