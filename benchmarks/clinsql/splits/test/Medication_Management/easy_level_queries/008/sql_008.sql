WITH
  antiplatelet_prescriptions AS (
    SELECT
      pr.hadm_id,
      pr.starttime,
      pr.stoptime,
      CASE
        WHEN LOWER(pr.drug) LIKE '%aspirin%' THEN 'aspirin'
        WHEN LOWER(pr.drug) LIKE '%clopidogrel%' OR LOWER(pr.drug) LIKE '%ticagrelor%' OR LOWER(pr.drug) LIKE '%prasugrel%' THEN 'p2y12_inhibitor'
      END AS drug_class
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON p.subject_id = pr.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 64 AND 74
      AND pr.starttime IS NOT NULL
      AND pr.stoptime IS NOT NULL
      AND (
        LOWER(pr.drug) LIKE '%aspirin%'
        OR LOWER(pr.drug) LIKE '%clopidogrel%'
        OR LOWER(pr.drug) LIKE '%ticagrelor%'
        OR LOWER(pr.drug) LIKE '%prasugrel%'
      )
  ),
  dapt_admissions AS (
    SELECT
      hadm_id
    FROM
      antiplatelet_prescriptions
    GROUP BY
      hadm_id
    HAVING
      COUNT(DISTINCT drug_class) = 2
  )
SELECT
  APPROX_QUANTILES(DATE_DIFF(DATE(ap.stoptime), DATE(ap.starttime), DAY), 2)[OFFSET(1)] AS median_dapt_prescription_duration_days
FROM
  antiplatelet_prescriptions AS ap
JOIN
  dapt_admissions AS da
  ON ap.hadm_id = da.hadm_id
WHERE
  DATE_DIFF(DATE(ap.stoptime), DATE(ap.starttime), DAY) > 0;
