WITH
  dapt_admissions AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions`
    WHERE
      hadm_id IS NOT NULL
    GROUP BY
      hadm_id
    HAVING
      COUNTIF(LOWER(drug) LIKE '%aspirin%') > 0
      AND
      COUNTIF(
        LOWER(drug) LIKE '%clopidogrel%' OR
        LOWER(drug) LIKE '%ticagrelor%' OR
        LOWER(drug) LIKE '%prasugrel%'
      ) > 0
  ),
  dapt_prescription_durations AS (
    SELECT
      DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) AS duration_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON p.subject_id = pr.subject_id
    JOIN
      dapt_admissions AS da
      ON pr.hadm_id = da.hadm_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 57 AND 67
      AND pr.starttime IS NOT NULL
      AND pr.stoptime IS NOT NULL
      AND DATE_DIFF(DATE(pr.stoptime), DATE(pr.starttime), DAY) >= 0
      AND (
        LOWER(pr.drug) LIKE '%aspirin%' OR
        LOWER(pr.drug) LIKE '%clopidogrel%' OR
        LOWER(pr.drug) LIKE '%ticagrelor%' OR
        LOWER(pr.drug) LIKE '%prasugrel%'
      )
  )
SELECT
  ROUND(
    (APPROX_QUANTILES(duration_days, 4)[OFFSET(3)]) - (APPROX_QUANTILES(duration_days, 4)[OFFSET(1)]),
    2
  ) AS iqr_dapt_prescription_duration_days
FROM
  dapt_prescription_durations
WHERE
  duration_days IS NOT NULL;
