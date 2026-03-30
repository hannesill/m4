-- ------------------------------------------------------------------
-- Title: Norepinephrine-Equivalent Vasopressor Dose
-- Calculates a normalized vasopressor dose combining 5 agents using
-- standard equivalence factors. Enables comparison across different
-- vasopressor types.
-- ------------------------------------------------------------------

-- Reference:
--    Goradia S et al. "Vasopressor dose equivalence: A scoping review
--    and suggested formula." J Crit Care. 2020;61:233-240.

-- Adapted from mimic-code norepinephrine_equivalent_dose.sql

SELECT
  stay_id,
  starttime,
  endtime,
  ROUND(
    TRY_CAST(COALESCE(norepinephrine, 0) + COALESCE(epinephrine, 0) + COALESCE(phenylephrine / 10, 0) + COALESCE(dopamine / 100, 0) + COALESCE(vasopressin * 2.5 / 60, 0) AS DECIMAL),
    4
  ) AS norepinephrine_equivalent_dose
FROM mimiciv_derived.vasoactive_agent
WHERE
  NOT norepinephrine IS NULL
  OR NOT epinephrine IS NULL
  OR NOT phenylephrine IS NULL
  OR NOT dopamine IS NULL
  OR NOT vasopressin IS NULL
