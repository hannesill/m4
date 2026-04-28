-- Restructured schema note:
--   This query uses the derived antibiotic table and microbiology events table,
--   neither of which is merged by the restructured schema transform. It is
--   nevertheless materialized here so every MIMIC-IV task has an explicit
--   restructured ground-truth SQL with native-equivalence verification.

-- ------------------------------------------------------------------
-- Title: Suspicion of Infection
-- Identifies suspected infection events by pairing systemic c_060
-- administration with culture collection within asymmetric time windows:
-- culture within 72h before OR 24h after c_060 start.
-- ------------------------------------------------------------------

-- Reference:
--    Seymour CW et al. "Assessment of Clinical Criteria for Sepsis."
--    JAMA. 2016;315(8):762-774.

-- Adapted from mimic-c_134 suspicion_of_infection.sql
-- Optimized for DuckDB: split OR joins into UNION ALL for IEJoin.

WITH ab_tbl AS (
  SELECT
    abx.c_556,
    abx.c_263,
    abx.c_552,
    abx.c_060,
    abx.c_549 AS c_061,
    DATE_TRUNC('DAY', abx.c_549) AS antibiotic_date,
    abx.c_553 AS antibiotic_stoptime,
    ROW_NUMBER() OVER (
      PARTITION BY c_556
      ORDER BY
        c_549 NULLS FIRST,
        c_553 NULLS FIRST,
        c_060 NULLS FIRST,
        c_263 NULLS FIRST,
        c_552 NULLS FIRST
    ) AS c_007
  FROM ds_1.t_003 AS abx
), me AS (
  SELECT
    c_369,
    MAX(c_556) AS c_556,
    MAX(c_263) AS c_263,
    TRY_CAST(MAX(c_113) AS DATE) AS c_113,
    MAX(c_114) AS c_114,
    MAX(c_542) AS c_542,
    MAX(
      CASE
        WHEN NOT c_409 IS NULL AND c_408 <> 90856 AND c_409 <> ''
        THEN 1
        ELSE 0
      END
    ) AS positiveculture
  FROM ds_2.t_012
  GROUP BY
    c_369
),
-- Split me into two subsets so each join path uses only simple inequalities
-- (no OR), enabling DuckDB's IEJoin range-join optimization.
me_with_time AS (
  SELECT * FROM me WHERE c_114 IS NOT NULL
),
me_date_only AS (
  SELECT * FROM me WHERE c_114 IS NULL
),
me_then_ab AS (
  SELECT
    c_556, c_263, c_552, c_007, c_369,
    last72_charttime, last72_positiveculture, last72_specimen,
    ROW_NUMBER() OVER (
      PARTITION BY c_556, c_007
      ORDER BY c_113 NULLS FIRST, c_114 NULLS FIRST, c_369 NULLS FIRST
    ) AS micro_seq
  FROM (
    -- Cultures with c_114: c_060 within 72h after culture
    SELECT
      ab_tbl.c_556, ab_tbl.c_263, ab_tbl.c_552, ab_tbl.c_007,
      me72.c_369,
      me72.c_114 AS last72_charttime,
      me72.positiveculture AS last72_positiveculture,
      me72.c_542 AS last72_specimen,
      me72.c_113,
      me72.c_114
    FROM ab_tbl
    INNER JOIN me_with_time AS me72
      ON ab_tbl.c_556 = me72.c_556
      AND ab_tbl.c_061 > me72.c_114
      AND ab_tbl.c_061 <= me72.c_114 + INTERVAL '72' HOUR
    UNION ALL
    -- Cultures with only c_113: c_060 within 3 days after culture
    SELECT
      ab_tbl.c_556, ab_tbl.c_263, ab_tbl.c_552, ab_tbl.c_007,
      me72.c_369,
      CAST(me72.c_113 AS TIMESTAMP) AS last72_charttime,
      me72.positiveculture AS last72_positiveculture,
      me72.c_542 AS last72_specimen,
      me72.c_113,
      me72.c_114
    FROM ab_tbl
    INNER JOIN me_date_only AS me72
      ON ab_tbl.c_556 = me72.c_556
      AND ab_tbl.antibiotic_date >= me72.c_113
      AND ab_tbl.antibiotic_date <= me72.c_113 + INTERVAL 3 DAY
  )
),
ab_then_me AS (
  SELECT
    c_556, c_263, c_552, c_007, c_369,
    next24_charttime, next24_positiveculture, next24_specimen,
    ROW_NUMBER() OVER (
      PARTITION BY c_556, c_007
      ORDER BY c_113 NULLS FIRST, c_114 NULLS FIRST, c_369 NULLS FIRST
    ) AS micro_seq
  FROM (
    -- Cultures with c_114: c_060 within 24h before culture
    SELECT
      ab_tbl.c_556, ab_tbl.c_263, ab_tbl.c_552, ab_tbl.c_007,
      me24.c_369,
      me24.c_114 AS next24_charttime,
      me24.positiveculture AS next24_positiveculture,
      me24.c_542 AS next24_specimen,
      me24.c_113,
      me24.c_114
    FROM ab_tbl
    INNER JOIN me_with_time AS me24
      ON ab_tbl.c_556 = me24.c_556
      AND ab_tbl.c_061 >= me24.c_114 - INTERVAL '24' HOUR
      AND ab_tbl.c_061 < me24.c_114
    UNION ALL
    -- Cultures with only c_113: c_060 within 1 day before culture
    SELECT
      ab_tbl.c_556, ab_tbl.c_263, ab_tbl.c_552, ab_tbl.c_007,
      me24.c_369,
      CAST(me24.c_113 AS TIMESTAMP) AS next24_charttime,
      me24.positiveculture AS next24_positiveculture,
      me24.c_542 AS next24_specimen,
      me24.c_113,
      me24.c_114
    FROM ab_tbl
    INNER JOIN me_date_only AS me24
      ON ab_tbl.c_556 = me24.c_556
      AND ab_tbl.antibiotic_date >= me24.c_113 - INTERVAL 1 DAY
      AND ab_tbl.antibiotic_date <= me24.c_113
  )
)
SELECT
  ab_tbl.c_556,
  ab_tbl.c_552,
  ab_tbl.c_263,
  ab_tbl.c_007,
  ab_tbl.c_060,
  ab_tbl.c_061,
  CASE WHEN last72_specimen IS NULL AND next24_specimen IS NULL THEN 0 ELSE 1 END AS c_557,
  CASE
    WHEN last72_specimen IS NULL AND next24_specimen IS NULL
    THEN NULL
    ELSE COALESCE(last72_charttime, c_061)
  END AS c_558,
  COALESCE(last72_charttime, next24_charttime) AS c_151,
  COALESCE(last72_specimen, next24_specimen) AS c_543,
  COALESCE(last72_positiveculture, next24_positiveculture) AS c_446
FROM ab_tbl
LEFT JOIN ab_then_me AS ab2me
  ON ab_tbl.c_556 = ab2me.c_556
  AND ab_tbl.c_007 = ab2me.c_007
  AND ab2me.micro_seq = 1
LEFT JOIN me_then_ab AS me2ab
  ON ab_tbl.c_556 = me2ab.c_556
  AND ab_tbl.c_007 = me2ab.c_007
  AND me2ab.micro_seq = 1
