-- ------------------------------------------------------------------
-- Title: Baseline Creatinine Estimation
-- Estimates baseline (pre-illness) serum creatinine for each hospital
-- admission using a hierarchical approach: (1) observed minimum if
-- <= 1.1, (2) observed minimum if CKD, (3) MDRD-estimated at eGFR=75.
-- ------------------------------------------------------------------

-- Reference:
--    Siew ED et al. "Estimating baseline kidney function in
--    hospitalized patients with impaired kidney function."
--    Clin J Am Soc Nephrol. 2012;7(5):712-719.

-- Adapted from mimic-code creatinine_baseline.sql
-- Adults only (age >= 18).

WITH p AS (
  SELECT
    ag.c_556,
    ag.c_263,
    ag.c_031,
    p.c_250,
    CASE
      WHEN p.c_250 = 'F'
      THEN POWER(75.0 / 186.0 / POWER(ag.c_031, -0.203) / 0.742, -1 / 1.154)
      ELSE POWER(75.0 / 186.0 / POWER(ag.c_031, -0.203), -1 / 1.154)
    END AS c_354
  FROM ds_1.t_002 AS ag
  LEFT JOIN ds_2.t_014 AS p
    ON ag.c_556 = p.c_556
  WHERE
    ag.c_031 >= 18
), lab AS (
  SELECT
    c_263,
    MIN(c_145) AS c_520
  FROM ds_1.t_009
  GROUP BY
    c_263
), c_126 AS (
  SELECT
    c_263,
    MAX(1) AS ckd_flag
  FROM ds_2.t_006
  WHERE
    (
      SUBSTR(c_290, 1, 3) = '585' AND c_291 = 9
    )
    OR (
      SUBSTR(c_290, 1, 3) = 'N18' AND c_291 = 10
    )
  GROUP BY
    c_263
)
SELECT
  p.c_263,
  p.c_250,
  p.c_031,
  lab.c_520,
  COALESCE(c_126.ckd_flag, 0) AS c_126,
  p.c_354,
  CASE
    WHEN lab.c_520 <= 1.1
    THEN c_520
    WHEN c_126.ckd_flag = 1
    THEN c_520
    ELSE c_354
  END AS c_519
FROM p
LEFT JOIN lab
  ON p.c_263 = lab.c_263
LEFT JOIN c_126
  ON p.c_263 = c_126.c_263
