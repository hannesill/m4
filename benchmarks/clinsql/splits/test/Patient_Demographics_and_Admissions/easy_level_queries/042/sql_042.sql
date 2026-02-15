WITH FirstCabgIcuStay AS (
  SELECT
    icu.los,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime, icu.intime) AS stay_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    ON p.subject_id = a.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.procedures_icd` AS proc
    ON a.hadm_id = proc.hadm_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
    ON a.hadm_id = icu.hadm_id
  WHERE
    p.gender = 'M'
    AND p.anchor_age BETWEEN 74 AND 84
    AND (proc.icd_code LIKE '361%' OR proc.icd_code LIKE '021%')
    AND icu.los IS NOT NULL
    AND a.dischtime IS NOT NULL
)
SELECT
  AVG(los) AS avg_icu_los_days_for_first_cabg
FROM
  FirstCabgIcuStay
WHERE
  stay_rank = 1;
