WITH FirstAkiIcuStay AS (
  SELECT
    icu.intime,
    icu.outtime,
    ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC, icu.intime ASC) as stay_rank
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` icu ON a.hadm_id = icu.hadm_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 82 AND 92
    AND icu.outtime IS NOT NULL
    AND a.hadm_id IN (
      SELECT DISTINCT hadm_id
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
      WHERE
        icd_code LIKE '584%' OR icd_code LIKE 'N17%'
    )
)
SELECT
  APPROX_QUANTILES(DATE_DIFF(DATE(outtime), DATE(intime), DAY), 100)[OFFSET(25)] AS p25_icu_los_days
FROM
  FirstAkiIcuStay
WHERE
  stay_rank = 1;
