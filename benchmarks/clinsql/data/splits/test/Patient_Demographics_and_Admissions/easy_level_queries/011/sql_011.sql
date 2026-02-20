WITH
  dapt_admissions AS (
    SELECT
      hadm_id
    FROM (
      SELECT
        hadm_id,
        CASE
          WHEN LOWER(drug) LIKE '%aspirin%' THEN 'aspirin'
          WHEN LOWER(drug) LIKE '%clopidogrel%' THEN 'clopidogrel'
          WHEN LOWER(drug) LIKE '%ticagrelor%' THEN 'ticagrelor'
          WHEN LOWER(drug) LIKE '%prasugrel%' THEN 'prasugrel'
          ELSE NULL
        END AS antiplatelet_agent
      FROM
        `physionet-data.mimiciv_3_1_hosp.prescriptions`
      WHERE
        LOWER(drug) LIKE '%aspirin%'
        OR LOWER(drug) LIKE '%clopidogrel%'
        OR LOWER(drug) LIKE '%ticagrelor%'
        OR LOWER(drug) LIKE '%prasugrel%'
    )
    WHERE
      antiplatelet_agent IS NOT NULL
    GROUP BY
      hadm_id
    HAVING
      COUNT(DISTINCT antiplatelet_agent) >= 2
  ),
  patient_first_admission AS (
    SELECT
      subject_id,
      hadm_id
    FROM (
      SELECT
        p.subject_id,
        a.hadm_id,
        ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) AS admission_rank
      FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
      JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
      WHERE
        p.gender = 'M'
        AND p.anchor_age BETWEEN 76 AND 86
        AND a.dischtime IS NOT NULL
    )
    WHERE
      admission_rank = 1
  ),
  icu_los_per_admission AS (
    SELECT
      hadm_id,
      SUM(DATETIME_DIFF(outtime, intime, HOUR)) / 24.0 AS total_icu_los_days
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays`
    WHERE
      intime IS NOT NULL AND outtime IS NOT NULL
    GROUP BY
      hadm_id
  )
SELECT
  AVG(icu.total_icu_los_days) AS avg_icu_length_of_stay_days
FROM
  patient_first_admission AS pfa
JOIN
  dapt_admissions AS da
  ON pfa.hadm_id = da.hadm_id
JOIN
  icu_los_per_admission AS icu
  ON pfa.hadm_id = icu.hadm_id;
