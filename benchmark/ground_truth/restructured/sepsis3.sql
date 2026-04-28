-- Restructured schema note:
--   This Sepsis-3 ground truth composes derived SOFA and suspicion-of-infection
--   tables, which are preserved under their obfuscated names in the
--   restructured source database. No merged base table is referenced here;
--   the SQL is kept separate so transformed-schema verification can compare
--   this task directly against native output.

-- ------------------------------------------------------------------
-- Title: Sepsis-3 Cohort Identification
-- Identifies sepsis patients using the Sepsis-3 consensus definition:
-- SOFA score >= 2 coinciding with suspected infection within a
-- 48h-before to 24h-after time window.
-- ------------------------------------------------------------------

-- Reference:
--    Singer M et al. "The Third International Consensus Definitions
--    for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.

-- Adapted from mimic-c_134 c_522.sql
-- Returns one row per ICU stay (earliest matching infection event).

WITH c_537 AS (
  SELECT
    c_552,
    c_549,
    c_212,
    c_499 AS c_498,
    c_133 AS c_132,
    c_330 AS c_329,
    c_107 AS c_106,
    c_131 AS c_130,
    c_488 AS c_487,
    c_538 AS c_539
  FROM ds_1.t_054
  WHERE
    c_538 >= 2
), s1 AS (
  SELECT
    soi.c_556,
    soi.c_552,
    soi.c_007,
    soi.c_060,
    soi.c_061,
    soi.c_151,
    soi.c_557,
    soi.c_558,
    soi.c_543,
    soi.c_446,
    c_549,
    c_212,
    c_498,
    c_132,
    c_329,
    c_106,
    c_130,
    c_487,
    c_539,
    CAST(c_539 >= 2 AND c_557 = 1 AS INTEGER) AS c_522,
    ROW_NUMBER() OVER (PARTITION BY soi.c_552 ORDER BY c_558 NULLS FIRST, c_061 NULLS FIRST, c_151 NULLS FIRST, c_212 NULLS FIRST) AS rn_sus
  FROM ds_1.t_055 AS soi
  INNER JOIN c_537
    ON soi.c_552 = c_537.c_552
    AND c_537.c_212 >= soi.c_558 - INTERVAL '48' HOUR
    AND c_537.c_212 <= soi.c_558 + INTERVAL '24' HOUR
  WHERE
    NOT soi.c_552 IS NULL
)
SELECT
  c_556,
  c_552,
  c_061,
  c_151,
  c_558,
  c_212 AS c_540,
  c_539,
  c_498,
  c_132,
  c_329,
  c_106,
  c_130,
  c_487,
  c_522
FROM s1
WHERE
  rn_sus = 1
