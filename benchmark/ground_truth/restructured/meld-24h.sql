-- Restructured: encounters replaces icustays (filter c_552 IS NOT NULL for ICU stays)

-- ------------------------------------------------------------------
-- Title: Model for End-Stage Liver Disease (MELD) score
-- This query extracts the MELD-Na score for the first 24 hours of
-- each ICU stay. MELD uses logarithmic transformations of creatinine,
-- bilirubin, and INR with a conditional sodium adjustment.
-- ------------------------------------------------------------------

-- Reference for MELD:
--    Kamath PS et al. "A model to predict survival in patients with
--    end-stage liver disease." Hepatology. 2001;33(2):464-470.
--    Kim WR et al. "Hyponatremia and mortality among patients on the
--    liver-transplant waiting list." NEJM. 2008;359(10):1018-1026.

-- Adapted from source MELD implementation

WITH cohort AS (
    SELECT
        ie.c_556,
        ie.c_263,
        ie.c_552,
        labs.c_146,
        labs.c_093,
        labs.c_306,
        labs.c_535,
        r.c_170 AS c_510
    FROM ds_2.t_901 AS ie
    LEFT JOIN ds_1.t_022 AS labs
        ON ie.c_552 = labs.c_552
    LEFT JOIN ds_1.t_023 AS r
        ON ie.c_552 = r.c_552
    WHERE ie.c_552 IS NOT NULL  -- encounters includes non-ICU admissions
)

, score AS (
    SELECT
        c_556, c_263, c_552,
        c_510, c_146, c_093, c_306, c_535,
        CASE
            WHEN c_535 IS NULL THEN 0.0
            WHEN c_535 > 137 THEN 0.0
            WHEN c_535 < 125 THEN 12.0
            ELSE 137.0 - c_535
        END AS c_536,
        CASE
            WHEN c_510 = 1 OR c_146 > 4.0
            THEN (0.957 * LN(4))
            WHEN c_146 < 1
            THEN (0.957 * LN(1))
            ELSE 0.957 * COALESCE(LN(c_146), LN(1))
        END AS c_148,
        CASE
            WHEN c_093 < 1
            THEN 0.378 * LN(1)
            ELSE 0.378 * COALESCE(LN(c_093), LN(1))
        END AS c_091,
        CASE
            WHEN c_306 < 1
            THEN (1.120 * LN(1) + 0.643)
            ELSE (1.120 * COALESCE(LN(c_306), LN(1)) + 0.643)
        END AS inr_score
    FROM cohort
)

, score2 AS (
    SELECT
        c_556, c_263, c_552,
        c_510, c_146, c_093, c_306, c_535,
        c_148, c_536, c_091, inr_score,
        CASE
            WHEN (c_148 + c_091 + inr_score) > 4
            THEN 40.0
            ELSE ROUND(TRY_CAST(c_148 + c_091 + inr_score AS DECIMAL), 1) * 10
        END AS c_361
    FROM score
)

SELECT
    c_556, c_263, c_552
    , CASE
        WHEN c_361 > 11
        THEN c_361 + 1.32 * c_536 - 0.033 * c_361 * c_536
        ELSE c_361
    END AS c_360
FROM score2
;
