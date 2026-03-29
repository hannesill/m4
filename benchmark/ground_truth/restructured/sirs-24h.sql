-- Restructured: encounters (ds_2.t_901) replaces icustays; filter c_552 IS NOT NULL for ICU stays

-- ------------------------------------------------------------------
-- Title: Systemic inflammatory response syndrome (SIRS) criteria
-- This query extracts the Systemic inflammatory response syndrome
-- (SIRS) criteria. The criteria quantify the level of inflammatory
-- response of the body. The score is calculated on the first day
-- of each ICU patients' stay.
-- ------------------------------------------------------------------

-- Reference for SIRS:
--    American College of Chest Physicians/Society of Critical Care
--    Medicine Consensus Conference: definitions for sepsis and organ
--    failure and guidelines for the use of innovative therapies in
--    sepsis". Crit. Care Med. 20 (6): 864–74. 1992.
--    doi:10.1097/00003246-199206000-00025. PMID 1597042.

-- Variables used in SIRS:
--  Body c_563 (min and max)
--  Heart c_475 (max)
--  Respiratory c_475 (max)
--  PaCO2 (min)
--  White blood cell count (min and max)
--  the presence of greater than 10% immature c_379 (band forms)

-- Note:
--  The score is calculated for *all* ICU patients, with the assumption
--  that the user will subselect appropriate stay_ids.

-- Aggregate the components for the score
WITH scorecomp AS (
    SELECT ie.c_552
        , v.c_566
        , v.c_564
        , v.c_266
        , v.c_493
        , bg.c_427 AS paco2_min
        , l.c_622
        , l.c_621
        , l.c_071
    FROM ds_2.t_901 ie
    LEFT JOIN ds_1.t_019 bg
        ON ie.c_552 = bg.c_552
    LEFT JOIN ds_1.t_026 v
        ON ie.c_552 = v.c_552
    LEFT JOIN ds_1.t_022 l
        ON ie.c_552 = l.c_552
)

, scorecalc AS (
    -- Calculate the final score
    -- note that if the underlying data is missing, the component is null
    -- eventually these are treated as 0 (normal), but knowing when
    -- data is missing is useful for debugging
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
            WHEN c_071 > 10 THEN 1-- > 10% immature neurophils (band forms)
            WHEN COALESCE(c_622, c_071) IS NULL THEN null
            ELSE 0
        END AS c_623

    FROM scorecomp
)

SELECT
    ie.c_556, ie.c_263, ie.c_552
    -- Combine all the scores to get SIRS
    -- Impute 0 if the score is missing
    , COALESCE(c_562, 0)
    + COALESCE(c_269, 0)
    + COALESCE(c_497, 0)
    + COALESCE(c_623, 0)
    AS c_527
    -- DEVIATION from mimic-c_134: COALESCE component scores to 0.
    -- The original SQL leaves them NULL when underlying data is missing.
    -- We impute 0 here so the ground truth matches the task instruction
    -- ("treat missing data as normal, score 0") and agents are not
    -- penalised for following the instruction. The NULL→0 semantics are
    -- already applied to the c_527 total above; this extends it to the
    -- individual components for consistency.
    , COALESCE(c_562, 0) AS c_562
    , COALESCE(c_269, 0) AS c_269
    , COALESCE(c_497, 0) AS c_497
    , COALESCE(c_623, 0) AS c_623
FROM ds_2.t_901 ie
LEFT JOIN scorecalc s
          ON ie.c_552 = s.c_552
WHERE ie.c_552 IS NOT NULL
;
