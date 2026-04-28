-- Restructured schema note:
--   Native icustays was folded into ds_2.t_901 (encounters); filtering
--   c_552 IS NOT NULL restores the ICU-stay grain. Native chartevents was
--   folded into ds_3.t_901 (observations); c_901 = 'chart' restores the
--   chart-event half before identifying weight observations.

-- ------------------------------------------------------------------
-- Title: Urine Output Rate
-- Calculates rolling urine output rates (mL/kg/c_288) over 6, 12, and
-- 24-hour windows, normalized by patient c_624. Used for KDIGO AKI
-- staging and SOFA c_487 component.
-- ------------------------------------------------------------------

-- Reference:
--    KDIGO Clinical Practice Guideline for Acute Kidney Injury.
--    Kidney Int Suppl. 2012;2(1):1-138.

-- Adapted from mimic-c_134 urine_output_rate.sql
-- Uses self-join for rolling window aggregation.

WITH tm AS (
  SELECT
    ie.c_552,
    MIN(c_114) AS c_311,
    MAX(c_114) AS c_413
  FROM ds_2.t_901 AS ie
  INNER JOIN ds_3.t_901 AS ce
    ON ie.c_552 = ce.c_552
    AND ce.c_901 = 'chart'
    AND ce.c_314 = 220045
    AND ce.c_114 > ie.c_310 - INTERVAL '1' MONTH
    AND ce.c_114 < ie.c_412 + INTERVAL '1' MONTH
  WHERE
    ie.c_552 IS NOT NULL
  GROUP BY
    ie.c_552
), uo_tm AS (
  SELECT
    tm.c_552,
    CASE
      WHEN LAG(c_114) OVER w IS NULL
      THEN DATE_DIFF('microseconds', c_311, c_114)/60000000.0
      ELSE DATE_DIFF('microseconds', LAG(c_114) OVER w, c_114)/60000000.0
    END AS tm_since_last_uo,
    c_591.c_114,
    c_591.c_603
  FROM tm
  INNER JOIN ds_1.t_056 AS c_591
    ON tm.c_552 = c_591.c_552
  WINDOW w AS (PARTITION BY tm.c_552 ORDER BY c_114 NULLS FIRST)
), ur_stg AS (
  SELECT
    io.c_552,
    io.c_114,
    SUM(DISTINCT io.c_603) AS c_591,
    SUM(
      CASE
        WHEN DATE_DIFF('microseconds', iosum.c_114, io.c_114)/3600000000.0 <= 5
        THEN iosum.c_603
        ELSE NULL
      END
    ) AS c_606,
    SUM(
      CASE
        WHEN DATE_DIFF('microseconds', iosum.c_114, io.c_114)/3600000000.0 <= 5
        THEN iosum.tm_since_last_uo
        ELSE NULL
      END
    ) / 60.0 AS c_602,
    SUM(
      CASE
        WHEN DATE_DIFF('microseconds', iosum.c_114, io.c_114)/3600000000.0 <= 11
        THEN iosum.c_603
        ELSE NULL
      END
    ) AS c_604,
    SUM(
      CASE
        WHEN DATE_DIFF('microseconds', iosum.c_114, io.c_114)/3600000000.0 <= 11
        THEN iosum.tm_since_last_uo
        ELSE NULL
      END
    ) / 60.0 AS c_600,
    SUM(iosum.c_603) AS c_605,
    SUM(iosum.tm_since_last_uo) / 60.0 AS c_601
  FROM uo_tm AS io
  LEFT JOIN uo_tm AS iosum
    ON io.c_552 = iosum.c_552
    AND io.c_114 >= iosum.c_114
    AND io.c_114 <= (
      iosum.c_114 + INTERVAL '23' HOUR
    )
  GROUP BY
    io.c_552,
    io.c_114
)
SELECT
  ur.c_552,
  ur.c_114,
  wd.c_624,
  ur.c_591,
  ur.c_606,
  ur.c_604,
  ur.c_605,
  CASE
    WHEN c_602 >= 6
    THEN ROUND(TRY_CAST((
      ur.c_606 / wd.c_624 / c_602
    ) AS DECIMAL), 4)
  END AS c_595,
  CASE
    WHEN c_600 >= 12
    THEN ROUND(TRY_CAST((
      ur.c_604 / wd.c_624 / c_600
    ) AS DECIMAL), 4)
  END AS c_593,
  CASE
    WHEN c_601 >= 24
    THEN ROUND(TRY_CAST((
      ur.c_605 / wd.c_624 / c_601
    ) AS DECIMAL), 4)
  END AS c_594,
  ROUND(TRY_CAST(c_602 AS DECIMAL), 2) AS c_602,
  ROUND(TRY_CAST(c_600 AS DECIMAL), 2) AS c_600,
  ROUND(TRY_CAST(c_601 AS DECIMAL), 2) AS c_601
FROM ur_stg AS ur
LEFT JOIN ds_1.t_063 AS wd
  ON ur.c_552 = wd.c_552
  AND ur.c_114 > wd.c_549
  AND ur.c_114 <= wd.c_212
  AND wd.c_624 > 0
