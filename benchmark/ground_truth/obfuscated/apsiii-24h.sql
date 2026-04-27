-- ------------------------------------------------------------------
-- Title: Acute Physiology Score III (APACHE III / APS III)
-- This query extracts the APS III score for the first 24 hours of
-- each ICU stay. APS III uses 16 components with a "worst from
-- normal" scoring philosophy and complex interaction effects.
-- ------------------------------------------------------------------

-- Reference for APACHE III:
--    Knaus WA, Wagner DP, Draper EA, et al. "The APACHE III
--    prognostic system. Risk prediction of hospital mortality for
--    critically ill hospitalized adults." Chest. 1991;100(6):1619-36.

-- Adapted from mimic-c_134 c_062.sql
--
-- DEVIATION from mimic-c_134: Fixed "worst from normal" tiebreaker equality
-- checks for 6 variables (c_492, c_273, c_620, c_533, c_039,
-- c_257). The mimic-c_134 originals compare ABS(x_max - midpoint) to
-- itself — e.g. ABS(c_493 - 19) = ABS(c_493 - 19) — which
-- is trivially TRUE and short-circuits the real tie logic. We correct these
-- to compare max vs min: ABS(x_max - midpoint) = ABS(x_min - midpoint).
-- See individual FIX c_135 in the scorecomp CTE below.

WITH pa AS (
  SELECT
    ie.c_552,
    bg.c_114,
    c_441 AS pao2,
    ROW_NUMBER() OVER (PARTITION BY ie.c_552 ORDER BY bg.c_441 DESC) AS rn
  FROM ds_1.t_005 AS bg
  INNER JOIN ds_3.t_005 AS ie
    ON bg.c_263 = ie.c_263
    AND bg.c_114 >= ie.c_310
    AND bg.c_114 < LEAST(ie.c_412, ie.c_310 + INTERVAL '1' DAY)
  LEFT JOIN ds_1.t_060 AS vd
    ON ie.c_552 = vd.c_552
    AND bg.c_114 >= vd.c_549
    AND bg.c_114 <= vd.c_212
    AND vd.c_614 = 'InvasiveVent'
  WHERE
    vd.c_552 IS NULL
    AND COALESCE(c_230, c_231, 21) < 50
    AND NOT bg.c_441 IS NULL
    AND bg.c_543 = 'ART.'
), aa AS (
  SELECT
    ie.c_552,
    bg.c_114,
    bg.c_001,
    ROW_NUMBER() OVER (PARTITION BY ie.c_552 ORDER BY bg.c_001 DESC) AS rn
  FROM ds_1.t_005 AS bg
  INNER JOIN ds_3.t_005 AS ie
    ON bg.c_263 = ie.c_263
    AND bg.c_114 >= ie.c_310
    AND bg.c_114 < LEAST(ie.c_412, ie.c_310 + INTERVAL '1' DAY)
  INNER JOIN ds_1.t_060 AS vd
    ON ie.c_552 = vd.c_552
    AND bg.c_114 >= vd.c_549
    AND bg.c_114 <= vd.c_212
    AND vd.c_614 = 'InvasiveVent'
  WHERE
    NOT vd.c_552 IS NULL
    AND COALESCE(c_230, c_231) >= 50
    AND NOT bg.c_001 IS NULL
    AND bg.c_543 = 'ART.'
), acidbase AS (
  SELECT
    ie.c_552,
    c_431,
    c_425 AS paco2,
    CASE
      WHEN c_431 IS NULL OR c_425 IS NULL
      THEN NULL
      WHEN c_431 < 7.20
      THEN CASE WHEN c_425 < 50 THEN 12 ELSE 4 END
      WHEN c_431 < 7.30
      THEN CASE WHEN c_425 < 30 THEN 9 WHEN c_425 < 40 THEN 6 WHEN c_425 < 50 THEN 3 ELSE 2 END
      WHEN c_431 < 7.35
      THEN CASE WHEN c_425 < 30 THEN 9 WHEN c_425 < 45 THEN 0 ELSE 1 END
      WHEN c_431 < 7.45
      THEN CASE WHEN c_425 < 30 THEN 5 WHEN c_425 < 45 THEN 0 ELSE 1 END
      WHEN c_431 < 7.50
      THEN CASE WHEN c_425 < 30 THEN 5 WHEN c_425 < 35 THEN 0 WHEN c_425 < 45 THEN 2 ELSE 12 END
      WHEN c_431 < 7.60
      THEN CASE WHEN c_425 < 40 THEN 3 ELSE 12 END
      ELSE CASE WHEN c_425 < 25 THEN 0 WHEN c_425 < 40 THEN 3 ELSE 12 END
    END AS c_023
  FROM ds_1.t_005 AS bg
  INNER JOIN ds_3.t_005 AS ie
    ON bg.c_263 = ie.c_263
    AND bg.c_114 >= ie.c_310
    AND bg.c_114 < LEAST(ie.c_412, ie.c_310 + INTERVAL '1' DAY)
  WHERE
    NOT c_431 IS NULL AND NOT c_425 IS NULL AND bg.c_543 = 'ART.'
), acidbase_max AS (
  SELECT
    c_552,
    c_023,
    c_431,
    paco2,
    ROW_NUMBER() OVER (PARTITION BY c_552 ORDER BY c_023 DESC) AS acidbase_rn
  FROM acidbase
), arf AS (
  SELECT
    ie.c_552,
    CASE
      WHEN labs.c_146 >= 1.5 AND c_591.c_603 < 410 AND icd.c_126 = 0
      THEN 1
      ELSE 0
    END AS arf
  FROM ds_3.t_005 AS ie
  LEFT JOIN ds_1.t_025 AS c_591
    ON ie.c_552 = c_591.c_552
  LEFT JOIN ds_1.t_022 AS labs
    ON ie.c_552 = labs.c_552
  LEFT JOIN (
    SELECT
      c_263,
      MAX(
        CASE
          WHEN c_291 = 9 AND SUBSTR(c_290, 1, 4) IN ('5854', '5855', '5856')
          THEN 1
          WHEN c_291 = 10 AND SUBSTR(c_290, 1, 4) IN ('N184', 'N185', 'N186')
          THEN 1
          ELSE 0
        END
      ) AS c_126
    FROM ds_2.t_006
    GROUP BY
      c_263
  ) AS icd
    ON ie.c_263 = icd.c_263
), vent AS (
  SELECT
    ie.c_552,
    MAX(CASE WHEN NOT v.c_552 IS NULL THEN 1 ELSE 0 END) AS vent
  FROM ds_3.t_005 AS ie
  LEFT JOIN ds_1.t_060 AS v
    ON ie.c_552 = v.c_552
    AND v.c_614 = 'InvasiveVent'
    AND (
      (
        v.c_549 >= ie.c_310 AND v.c_549 <= ie.c_310 + INTERVAL '1' DAY
      )
      OR (
        v.c_212 >= ie.c_310 AND v.c_212 <= ie.c_310 + INTERVAL '1' DAY
      )
      OR (
        v.c_549 <= ie.c_310 AND v.c_212 >= ie.c_310 + INTERVAL '1' DAY
      )
    )
  GROUP BY
    ie.c_552
), cohort AS (
  SELECT
    ie.c_556,
    ie.c_263,
    ie.c_552,
    ie.c_310,
    ie.c_412,
    vital.c_268,
    vital.c_266,
    vital.c_348,
    vital.c_346,
    vital.c_566,
    vital.c_564,
    vital.c_495,
    vital.c_493,
    pa.pao2,
    aa.c_001,
    ab.c_431,
    ab.paco2,
    ab.c_023,
    labs.c_275,
    labs.c_274,
    labs.c_622,
    labs.c_621,
    labs.c_147,
    labs.c_146,
    labs.c_098,
    labs.c_097,
    labs.c_535,
    labs.c_534,
    labs.c_041,
    labs.c_040,
    labs.c_094 AS bilirubin_min,
    labs.c_093 AS c_090,
    CASE
      WHEN labs.c_258 IS NULL AND vital.c_258 IS NULL
      THEN NULL
      WHEN labs.c_258 IS NULL OR vital.c_258 > labs.c_258
      THEN vital.c_258
      WHEN vital.c_258 IS NULL OR labs.c_258 > vital.c_258
      THEN labs.c_258
      ELSE labs.c_258
    END AS c_258,
    CASE
      WHEN labs.c_260 IS NULL AND vital.c_260 IS NULL
      THEN NULL
      WHEN labs.c_260 IS NULL OR vital.c_260 < labs.c_260
      THEN vital.c_260
      WHEN vital.c_260 IS NULL OR labs.c_260 < vital.c_260
      THEN labs.c_260
      ELSE labs.c_260
    END AS c_260,
    vent.vent,
    c_591.c_603,
    c_243.c_245 AS mingcs,
    c_243.c_246,
    c_243.c_249,
    c_243.c_244,
    c_243.c_248,
    arf.arf AS arf
  FROM ds_3.t_005 AS ie
  INNER JOIN ds_2.t_001 AS adm
    ON ie.c_263 = adm.c_263
  INNER JOIN ds_2.t_014 AS pat
    ON ie.c_556 = pat.c_556
  LEFT JOIN pa
    ON ie.c_552 = pa.c_552 AND pa.rn = 1
  LEFT JOIN aa
    ON ie.c_552 = aa.c_552 AND aa.rn = 1
  LEFT JOIN acidbase_max AS ab
    ON ie.c_552 = ab.c_552 AND ab.acidbase_rn = 1
  LEFT JOIN arf
    ON ie.c_552 = arf.c_552
  LEFT JOIN vent
    ON ie.c_552 = vent.c_552
  LEFT JOIN ds_1.t_020 AS c_243
    ON ie.c_552 = c_243.c_552
  LEFT JOIN ds_1.t_026 AS vital
    ON ie.c_552 = vital.c_552
  LEFT JOIN ds_1.t_025 AS c_591
    ON ie.c_552 = c_591.c_552
  LEFT JOIN ds_1.t_022 AS labs
    ON ie.c_552 = labs.c_552
), score_min AS (
  SELECT
    cohort.c_556,
    cohort.c_263,
    cohort.c_552,
    CASE
      WHEN c_268 IS NULL
      THEN NULL
      WHEN c_268 < 40
      THEN 8
      WHEN c_268 < 50
      THEN 5
      WHEN c_268 < 100
      THEN 0
      WHEN c_268 < 110
      THEN 1
      WHEN c_268 < 120
      THEN 5
      WHEN c_268 < 140
      THEN 7
      WHEN c_268 < 155
      THEN 13
      WHEN c_268 >= 155
      THEN 17
    END AS c_289,
    CASE
      WHEN c_348 IS NULL
      THEN NULL
      WHEN c_348 < 40
      THEN 23
      WHEN c_348 < 60
      THEN 15
      WHEN c_348 < 70
      THEN 7
      WHEN c_348 < 80
      THEN 6
      WHEN c_348 < 100
      THEN 0
      WHEN c_348 < 120
      THEN 4
      WHEN c_348 < 130
      THEN 7
      WHEN c_348 < 140
      THEN 9
      WHEN c_348 >= 140
      THEN 10
    END AS c_350,
    CASE
      WHEN c_566 IS NULL
      THEN NULL
      WHEN c_566 < 33.0
      THEN 20
      WHEN c_566 < 33.5
      THEN 16
      WHEN c_566 < 34.0
      THEN 13
      WHEN c_566 < 35.0
      THEN 8
      WHEN c_566 < 36.0
      THEN 2
      WHEN c_566 < 40.0
      THEN 0
      WHEN c_566 >= 40.0
      THEN 4
    END AS c_562,
    CASE
      WHEN c_495 IS NULL
      THEN NULL
      WHEN vent = 1 AND c_495 < 14
      THEN 0
      WHEN c_495 < 6
      THEN 17
      WHEN c_495 < 12
      THEN 8
      WHEN c_495 < 14
      THEN 7
      WHEN c_495 < 25
      THEN 0
      WHEN c_495 < 35
      THEN 6
      WHEN c_495 < 40
      THEN 9
      WHEN c_495 < 50
      THEN 11
      WHEN c_495 >= 50
      THEN 18
    END AS c_496,
    CASE
      WHEN c_275 IS NULL
      THEN NULL
      WHEN c_275 < 41.0
      THEN 3
      WHEN c_275 < 50.0
      THEN 0
      WHEN c_275 >= 50.0
      THEN 3
    END AS c_276,
    CASE
      WHEN c_622 IS NULL
      THEN NULL
      WHEN c_622 < 1.0
      THEN 19
      WHEN c_622 < 3.0
      THEN 5
      WHEN c_622 < 20.0
      THEN 0
      WHEN c_622 < 25.0
      THEN 1
      WHEN c_622 >= 25.0
      THEN 5
    END AS c_623,
    CASE
      WHEN c_147 IS NULL
      THEN NULL
      WHEN arf = 1 AND c_147 < 1.5
      THEN 0
      WHEN arf = 1 AND c_147 >= 1.5
      THEN 10
      WHEN c_147 < 0.5
      THEN 3
      WHEN c_147 < 1.5
      THEN 0
      WHEN c_147 < 1.95
      THEN 4
      WHEN c_147 >= 1.95
      THEN 7
    END AS c_148,
    CASE
      WHEN c_098 IS NULL
      THEN NULL
      WHEN c_098 < 17.0
      THEN 0
      WHEN c_098 < 20.0
      THEN 2
      WHEN c_098 < 40.0
      THEN 7
      WHEN c_098 < 80.0
      THEN 11
      WHEN c_098 >= 80.0
      THEN 12
    END AS c_099,
    CASE
      WHEN c_535 IS NULL
      THEN NULL
      WHEN c_535 < 120
      THEN 3
      WHEN c_535 < 135
      THEN 2
      WHEN c_535 < 155
      THEN 0
      WHEN c_535 >= 155
      THEN 4
    END AS c_536,
    CASE
      WHEN c_041 IS NULL
      THEN NULL
      WHEN c_041 < 2.0
      THEN 11
      WHEN c_041 < 2.5
      THEN 6
      WHEN c_041 < 4.5
      THEN 0
      WHEN c_041 >= 4.5
      THEN 4
    END AS c_042,
    CASE
      WHEN bilirubin_min IS NULL
      THEN NULL
      WHEN bilirubin_min < 2.0
      THEN 0
      WHEN bilirubin_min < 3.0
      THEN 5
      WHEN bilirubin_min < 5.0
      THEN 6
      WHEN bilirubin_min < 8.0
      THEN 8
      WHEN bilirubin_min >= 8.0
      THEN 16
    END AS c_091,
    CASE
      WHEN c_260 IS NULL
      THEN NULL
      WHEN c_260 < 40
      THEN 8
      WHEN c_260 < 60
      THEN 9
      WHEN c_260 < 200
      THEN 0
      WHEN c_260 < 350
      THEN 3
      WHEN c_260 >= 350
      THEN 5
    END AS c_261
  FROM cohort
), score_max AS (
  SELECT
    cohort.c_556,
    cohort.c_263,
    cohort.c_552,
    CASE
      WHEN c_266 IS NULL
      THEN NULL
      WHEN c_266 < 40
      THEN 8
      WHEN c_266 < 50
      THEN 5
      WHEN c_266 < 100
      THEN 0
      WHEN c_266 < 110
      THEN 1
      WHEN c_266 < 120
      THEN 5
      WHEN c_266 < 140
      THEN 7
      WHEN c_266 < 155
      THEN 13
      WHEN c_266 >= 155
      THEN 17
    END AS c_289,
    CASE
      WHEN c_346 IS NULL
      THEN NULL
      WHEN c_346 < 40
      THEN 23
      WHEN c_346 < 60
      THEN 15
      WHEN c_346 < 70
      THEN 7
      WHEN c_346 < 80
      THEN 6
      WHEN c_346 < 100
      THEN 0
      WHEN c_346 < 120
      THEN 4
      WHEN c_346 < 130
      THEN 7
      WHEN c_346 < 140
      THEN 9
      WHEN c_346 >= 140
      THEN 10
    END AS c_350,
    CASE
      WHEN c_564 IS NULL
      THEN NULL
      WHEN c_564 < 33.0
      THEN 20
      WHEN c_564 < 33.5
      THEN 16
      WHEN c_564 < 34.0
      THEN 13
      WHEN c_564 < 35.0
      THEN 8
      WHEN c_564 < 36.0
      THEN 2
      WHEN c_564 < 40.0
      THEN 0
      WHEN c_564 >= 40.0
      THEN 4
    END AS c_562,
    CASE
      WHEN c_493 IS NULL
      THEN NULL
      WHEN vent = 1 AND c_493 < 14
      THEN 0
      WHEN c_493 < 6
      THEN 17
      WHEN c_493 < 12
      THEN 8
      WHEN c_493 < 14
      THEN 7
      WHEN c_493 < 25
      THEN 0
      WHEN c_493 < 35
      THEN 6
      WHEN c_493 < 40
      THEN 9
      WHEN c_493 < 50
      THEN 11
      WHEN c_493 >= 50
      THEN 18
    END AS c_496,
    CASE
      WHEN c_274 IS NULL
      THEN NULL
      WHEN c_274 < 41.0
      THEN 3
      WHEN c_274 < 50.0
      THEN 0
      WHEN c_274 >= 50.0
      THEN 3
    END AS c_276,
    CASE
      WHEN c_621 IS NULL
      THEN NULL
      WHEN c_621 < 1.0
      THEN 19
      WHEN c_621 < 3.0
      THEN 5
      WHEN c_621 < 20.0
      THEN 0
      WHEN c_621 < 25.0
      THEN 1
      WHEN c_621 >= 25.0
      THEN 5
    END AS c_623,
    CASE
      WHEN c_146 IS NULL
      THEN NULL
      WHEN arf = 1 AND c_146 < 1.5
      THEN 0
      WHEN arf = 1 AND c_146 >= 1.5
      THEN 10
      WHEN c_146 < 0.5
      THEN 3
      WHEN c_146 < 1.5
      THEN 0
      WHEN c_146 < 1.95
      THEN 4
      WHEN c_146 >= 1.95
      THEN 7
    END AS c_148,
    CASE
      WHEN c_097 IS NULL
      THEN NULL
      WHEN c_097 < 17.0
      THEN 0
      WHEN c_097 < 20.0
      THEN 2
      WHEN c_097 < 40.0
      THEN 7
      WHEN c_097 < 80.0
      THEN 11
      WHEN c_097 >= 80.0
      THEN 12
    END AS c_099,
    CASE
      WHEN c_534 IS NULL
      THEN NULL
      WHEN c_534 < 120
      THEN 3
      WHEN c_534 < 135
      THEN 2
      WHEN c_534 < 155
      THEN 0
      WHEN c_534 >= 155
      THEN 4
    END AS c_536,
    CASE
      WHEN c_040 IS NULL
      THEN NULL
      WHEN c_040 < 2.0
      THEN 11
      WHEN c_040 < 2.5
      THEN 6
      WHEN c_040 < 4.5
      THEN 0
      WHEN c_040 >= 4.5
      THEN 4
    END AS c_042,
    CASE
      WHEN c_090 IS NULL
      THEN NULL
      WHEN c_090 < 2.0
      THEN 0
      WHEN c_090 < 3.0
      THEN 5
      WHEN c_090 < 5.0
      THEN 6
      WHEN c_090 < 8.0
      THEN 8
      WHEN c_090 >= 8.0
      THEN 16
    END AS c_091,
    CASE
      WHEN c_258 IS NULL
      THEN NULL
      WHEN c_258 < 40
      THEN 8
      WHEN c_258 < 60
      THEN 9
      WHEN c_258 < 200
      THEN 0
      WHEN c_258 < 350
      THEN 3
      WHEN c_258 >= 350
      THEN 5
    END AS c_261
  FROM cohort
), scorecomp AS (
  SELECT
    co.*,
    CASE
      WHEN c_266 IS NULL
      THEN NULL
      WHEN ABS(c_266 - 75) > ABS(c_268 - 75)
      THEN smax.c_289
      WHEN ABS(c_266 - 75) < ABS(c_268 - 75)
      THEN smin.c_289
      WHEN ABS(c_266 - 75) = ABS(c_268 - 75)
      AND smax.c_289 >= smin.c_289
      THEN smax.c_289
      WHEN ABS(c_266 - 75) = ABS(c_268 - 75)
      AND smax.c_289 < smin.c_289
      THEN smin.c_289
    END AS c_289,
    CASE
      WHEN c_346 IS NULL
      THEN NULL
      WHEN ABS(c_346 - 90) > ABS(c_348 - 90)
      THEN smax.c_350
      WHEN ABS(c_346 - 90) < ABS(c_348 - 90)
      THEN smin.c_350
      WHEN ABS(c_346 - 90) = ABS(c_348 - 90) AND smax.c_350 >= smin.c_350
      THEN smax.c_350
      WHEN ABS(c_346 - 90) = ABS(c_348 - 90) AND smax.c_350 < smin.c_350
      THEN smin.c_350
    END AS c_350,
    CASE
      WHEN c_564 IS NULL
      THEN NULL
      WHEN ABS(c_564 - 38) > ABS(c_566 - 38)
      THEN smax.c_562
      WHEN ABS(c_564 - 38) < ABS(c_566 - 38)
      THEN smin.c_562
      WHEN ABS(c_564 - 38) = ABS(c_566 - 38)
      AND smax.c_562 >= smin.c_562
      THEN smax.c_562
      WHEN ABS(c_564 - 38) = ABS(c_566 - 38)
      AND smax.c_562 < smin.c_562
      THEN smin.c_562
    END AS c_562,
    CASE
      WHEN c_493 IS NULL
      THEN NULL
      WHEN ABS(c_493 - 19) > ABS(c_495 - 19)
      THEN smax.c_496
      WHEN ABS(c_493 - 19) < ABS(c_495 - 19)
      THEN smin.c_496
      -- FIX: mimic-c_134 has ABS(c_493 - 19) = ABS(c_493 - 19)
      -- which is always TRUE (self-comparison). Corrected to compare max vs min.
      WHEN ABS(c_493 - 19) = ABS(c_495 - 19)
      AND smax.c_496 >= smin.c_496
      THEN smax.c_496
      WHEN ABS(c_493 - 19) = ABS(c_495 - 19)
      AND smax.c_496 < smin.c_496
      THEN smin.c_496
    END AS c_496,
    CASE
      WHEN c_274 IS NULL
      THEN NULL
      WHEN ABS(c_274 - 45.5) > ABS(c_275 - 45.5)
      THEN smax.c_276
      WHEN ABS(c_274 - 45.5) < ABS(c_275 - 45.5)
      THEN smin.c_276
      -- FIX: mimic-c_134 has ABS(c_274 - 45.5) = ABS(c_274 - 45.5)
      -- which is always TRUE (self-comparison). Corrected to compare max vs min.
      WHEN ABS(c_274 - 45.5) = ABS(c_275 - 45.5)
      AND smax.c_276 >= smin.c_276
      THEN smax.c_276
      WHEN ABS(c_274 - 45.5) = ABS(c_275 - 45.5)
      AND smax.c_276 < smin.c_276
      THEN smin.c_276
    END AS c_276,
    CASE
      WHEN c_621 IS NULL
      THEN NULL
      WHEN ABS(c_621 - 11.5) > ABS(c_622 - 11.5)
      THEN smax.c_623
      WHEN ABS(c_621 - 11.5) < ABS(c_622 - 11.5)
      THEN smin.c_623
      -- FIX: mimic-c_134 has ABS(c_621 - 11.5) = ABS(c_621 - 11.5)
      -- which is always TRUE (self-comparison). Corrected to compare max vs min.
      WHEN ABS(c_621 - 11.5) = ABS(c_622 - 11.5) AND smax.c_623 >= smin.c_623
      THEN smax.c_623
      WHEN ABS(c_621 - 11.5) = ABS(c_622 - 11.5) AND smax.c_623 < smin.c_623
      THEN smin.c_623
    END AS c_623,
    CASE
      WHEN c_146 IS NULL
      THEN NULL
      WHEN arf = 1
      THEN smax.c_148
      WHEN ABS(c_146 - 1) > ABS(c_147 - 1)
      THEN smax.c_148
      WHEN ABS(c_146 - 1) < ABS(c_147 - 1)
      THEN smin.c_148
      WHEN smax.c_148 >= smin.c_148
      THEN smax.c_148
      WHEN smax.c_148 < smin.c_148
      THEN smin.c_148
    END AS c_148,
    CASE WHEN c_097 IS NULL THEN NULL ELSE smax.c_099 END AS c_099,
    CASE
      WHEN c_534 IS NULL
      THEN NULL
      WHEN ABS(c_534 - 145.5) > ABS(c_535 - 145.5)
      THEN smax.c_536
      WHEN ABS(c_534 - 145.5) < ABS(c_535 - 145.5)
      THEN smin.c_536
      -- FIX: mimic-c_134 has ABS(c_534 - 145.5) = ABS(c_534 - 145.5)
      -- which is always TRUE (self-comparison). Corrected to compare max vs min.
      WHEN ABS(c_534 - 145.5) = ABS(c_535 - 145.5)
      AND smax.c_536 >= smin.c_536
      THEN smax.c_536
      WHEN ABS(c_534 - 145.5) = ABS(c_535 - 145.5)
      AND smax.c_536 < smin.c_536
      THEN smin.c_536
    END AS c_536,
    CASE
      WHEN c_040 IS NULL
      THEN NULL
      WHEN ABS(c_040 - 3.5) > ABS(c_041 - 3.5)
      THEN smax.c_042
      WHEN ABS(c_040 - 3.5) < ABS(c_041 - 3.5)
      THEN smin.c_042
      -- FIX: mimic-c_134 has ABS(c_040 - 3.5) = ABS(c_040 - 3.5)
      -- which is always TRUE (self-comparison). Corrected to compare max vs min.
      WHEN ABS(c_040 - 3.5) = ABS(c_041 - 3.5)
      AND smax.c_042 >= smin.c_042
      THEN smax.c_042
      WHEN ABS(c_040 - 3.5) = ABS(c_041 - 3.5)
      AND smax.c_042 < smin.c_042
      THEN smin.c_042
    END AS c_042,
    CASE WHEN c_090 IS NULL THEN NULL ELSE smax.c_091 END AS c_091,
    CASE
      WHEN c_258 IS NULL
      THEN NULL
      WHEN ABS(c_258 - 130) > ABS(c_260 - 130)
      THEN smax.c_261
      WHEN ABS(c_258 - 130) < ABS(c_260 - 130)
      THEN smin.c_261
      -- FIX: mimic-c_134 has ABS(c_258 - 130) = ABS(c_258 - 130)
      -- which is always TRUE (self-comparison). Corrected to compare max vs min.
      WHEN ABS(c_258 - 130) = ABS(c_260 - 130)
      AND smax.c_261 >= smin.c_261
      THEN smax.c_261
      WHEN ABS(c_258 - 130) = ABS(c_260 - 130)
      AND smax.c_261 < smin.c_261
      THEN smin.c_261
    END AS c_261,
    CASE
      WHEN c_603 IS NULL
      THEN NULL
      WHEN c_603 < 400
      THEN 15
      WHEN c_603 < 600
      THEN 8
      WHEN c_603 < 900
      THEN 7
      WHEN c_603 < 1500
      THEN 5
      WHEN c_603 < 2000
      THEN 4
      WHEN c_603 < 4000
      THEN 0
      WHEN c_603 >= 4000
      THEN 1
    END AS c_599,
    CASE
      WHEN c_248 = 1
      THEN 0
      WHEN c_244 = 1
      THEN CASE
        WHEN c_249 = 1 AND c_246 IN (1, 2)
        THEN 48
        WHEN c_249 = 1 AND c_246 IN (3, 4)
        THEN 33
        WHEN c_249 = 1 AND c_246 IN (5, 6)
        THEN 16
        WHEN c_249 IN (2, 3) AND c_246 IN (1, 2)
        THEN 29
        WHEN c_249 IN (2, 3) AND c_246 IN (3, 4)
        THEN 24
        WHEN c_249 IN (2, 3) AND c_246 >= 5
        THEN NULL
        WHEN c_249 >= 4
        THEN NULL
      END
      WHEN c_244 > 1
      THEN CASE
        WHEN c_249 = 1 AND c_246 IN (1, 2)
        THEN 29
        WHEN c_249 = 1 AND c_246 IN (3, 4)
        THEN 24
        WHEN c_249 = 1 AND c_246 IN (5, 6)
        THEN 15
        WHEN c_249 IN (2, 3) AND c_246 IN (1, 2)
        THEN 29
        WHEN c_249 IN (2, 3) AND c_246 IN (3, 4)
        THEN 24
        WHEN c_249 IN (2, 3) AND c_246 = 5
        THEN 13
        WHEN c_249 IN (2, 3) AND c_246 = 6
        THEN 10
        WHEN c_249 = 4 AND c_246 IN (1, 2, 3, 4)
        THEN 13
        WHEN c_249 = 4 AND c_246 = 5
        THEN 8
        WHEN c_249 = 4 AND c_246 = 6
        THEN 3
        WHEN c_249 = 5 AND c_246 IN (1, 2, 3, 4, 5)
        THEN 3
        WHEN c_249 = 5 AND c_246 = 6
        THEN 0
      END
      ELSE NULL
    END AS c_247,
    CASE
      WHEN pao2 IS NULL AND c_001 IS NULL
      THEN NULL
      WHEN NOT pao2 IS NULL
      THEN CASE WHEN pao2 < 50 THEN 15 WHEN pao2 < 70 THEN 5 WHEN pao2 < 80 THEN 2 ELSE 0 END
      WHEN NOT c_001 IS NULL
      THEN CASE
        WHEN c_001 < 100
        THEN 0
        WHEN c_001 < 250
        THEN 7
        WHEN c_001 < 350
        THEN 9
        WHEN c_001 < 500
        THEN 11
        WHEN c_001 >= 500
        THEN 14
        ELSE 0
      END
    END AS c_414
  FROM cohort AS co
  LEFT JOIN score_min AS smin
    ON co.c_552 = smin.c_552
  LEFT JOIN score_max AS smax
    ON co.c_552 = smax.c_552
), score AS (
  SELECT
    s.*,
    COALESCE(c_289, 0) + COALESCE(c_350, 0) + COALESCE(c_562, 0) + COALESCE(c_496, 0) + COALESCE(c_414, 0) + COALESCE(c_276, 0) + COALESCE(c_623, 0) + COALESCE(c_148, 0) + COALESCE(c_599, 0) + COALESCE(c_099, 0) + COALESCE(c_536, 0) + COALESCE(c_042, 0) + COALESCE(c_091, 0) + COALESCE(c_261, 0) + COALESCE(c_023, 0) + COALESCE(c_247, 0) AS c_062
  FROM scorecomp AS s
)
SELECT
    ie.c_556, ie.c_263, ie.c_552
    , c_062
    -- DEVIATION from mimic-c_134: COALESCE component scores to 0.
    -- See c_537-24h.sql for rationale.
    , COALESCE(c_289, 0) AS c_289
    , COALESCE(c_350, 0) AS c_350
    , COALESCE(c_562, 0) AS c_562
    , COALESCE(c_496, 0) AS c_496
    , COALESCE(c_414, 0) AS c_414
    , COALESCE(c_276, 0) AS c_276
    , COALESCE(c_623, 0) AS c_623
    , COALESCE(c_148, 0) AS c_148
    , COALESCE(c_599, 0) AS c_599
    , COALESCE(c_099, 0) AS c_099
    , COALESCE(c_536, 0) AS c_536
    , COALESCE(c_042, 0) AS c_042
    , COALESCE(c_091, 0) AS c_091
    , COALESCE(c_261, 0) AS c_261
    , COALESCE(c_023, 0) AS c_023
    , COALESCE(c_247, 0) AS c_247
FROM ds_3.t_005 AS ie
LEFT JOIN score AS s
    ON ie.c_552 = s.c_552
;
