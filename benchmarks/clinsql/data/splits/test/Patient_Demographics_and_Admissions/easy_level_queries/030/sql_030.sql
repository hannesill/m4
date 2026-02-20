WITH FirstAdmissions AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) AS admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 52 AND 62
    AND a.dischtime IS NOT NULL
    AND a.admittime IS NOT NULL
)
SELECT
  STDDEV_SAMP(fa.length_of_stay) AS stddev_los_days
FROM
  FirstAdmissions AS fa
WHERE
  fa.admission_rank = 1
  AND fa.hadm_id IN (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.prescriptions`
    WHERE
      LOWER(drug) LIKE '%heparin%'
      OR LOWER(drug) LIKE '%warfarin%'
      OR LOWER(drug) LIKE '%enoxaparin%'
      OR LOWER(drug) LIKE '%lovenox%'
      OR LOWER(drug) LIKE '%argatroban%'
      OR LOWER(drug) LIKE '%fondaparinux%'
      OR LOWER(drug) LIKE '%arixtra%'
      OR LOWER(drug) LIKE '%rivaroxaban%'
      OR LOWER(drug) LIKE '%xarelto%'
      OR LOWER(drug) LIKE '%apixaban%'
      OR LOWER(drug) LIKE '%eliquis%'
      OR LOWER(drug) LIKE '%dabigatran%'
      OR LOWER(drug) LIKE '%pradaxa%'
  );
