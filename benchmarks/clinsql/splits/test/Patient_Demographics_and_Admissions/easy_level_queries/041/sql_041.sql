WITH first_admissions AS (
  SELECT
    p.subject_id,
    a.hadm_id,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) as admission_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 50 AND 60
),
admissions_with_anticoagulants AS (
  SELECT
    fa.hadm_id
  FROM
    first_admissions AS fa
  WHERE
    fa.admission_rank = 1
    AND EXISTS (
      SELECT 1
      FROM `physionet-data.mimiciv_3_1_hosp.prescriptions` AS rx
      WHERE rx.hadm_id = fa.hadm_id
      AND (
           LOWER(rx.drug) LIKE '%heparin%'
        OR LOWER(rx.drug) LIKE '%warfarin%'
        OR LOWER(rx.drug) LIKE '%coumadin%'
        OR LOWER(rx.drug) LIKE '%enoxaparin%'
        OR LOWER(rx.drug) LIKE '%lovenox%'
        OR LOWER(rx.drug) LIKE '%apixaban%'
        OR LOWER(rx.drug) LIKE '%eliquis%'
        OR LOWER(rx.drug) LIKE '%rivaroxaban%'
        OR LOWER(rx.drug) LIKE '%xarelto%'
      )
    )
),
icu_stays_los AS (
  SELECT
    DATETIME_DIFF(icu.outtime, icu.intime, DAY) AS icu_los_days,
    ROW_NUMBER() OVER(PARTITION BY icu.hadm_id ORDER BY icu.intime ASC) as icu_stay_rank
  FROM
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  JOIN
    admissions_with_anticoagulants AS aa
    ON icu.hadm_id = aa.hadm_id
  WHERE
    icu.outtime IS NOT NULL
)
SELECT
  APPROX_QUANTILES(icu_los_days, 2)[OFFSET(1)] AS median_icu_los_days
FROM
  icu_stays_los
WHERE
  icu_stay_rank = 1;
