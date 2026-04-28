-- Restructured schema note:
--   This task reads the derived vasoactive-agent interval table, which is
--   preserved under its obfuscated name in the restructured source database.
--   No merged base table is required, but the SQL lives here to make the
--   restructured ground-truth set complete and directly verifiable.

-- ------------------------------------------------------------------
-- Title: Norepinephrine-Equivalent Vasopressor Dose
-- Calculates a normalized vasopressor dose combining 5 agents using
-- standard equivalence factors. Enables comparison across different
-- vasopressor types.
-- ------------------------------------------------------------------

-- Reference:
--    Goradia S et al. "Vasopressor dose equivalence: A scoping review
--    and suggested formula." J Crit Care. 2020;61:233-240.

-- Adapted from mimic-c_134 c_384.sql
-- DEVIATION from mimic-code: the source interval table can contain duplicate
-- rows for the same stay/start/end interval. The benchmark key is
-- interval-level, so duplicates are collapsed with MAX dose to provide one
-- deterministic target row per interval.

SELECT
  c_552,
  c_549,
  c_212,
  MAX(ROUND(
    TRY_CAST(COALESCE(c_383, 0) + COALESCE(c_217, 0) + COALESCE(c_435 / 10, 0) + COALESCE(c_183 / 100, 0) + COALESCE(c_613 * 2.5 / 60, 0) AS DECIMAL),
    4
  )) AS c_384
FROM ds_1.t_058
WHERE
  NOT c_383 IS NULL
  OR NOT c_217 IS NULL
  OR NOT c_435 IS NULL
  OR NOT c_183 IS NULL
  OR NOT c_613 IS NULL
GROUP BY c_552, c_549, c_212
