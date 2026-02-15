WITH
  AdmissionsWithDiagnoses AS (
    SELECT
      a.hadm_id,
      DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND p.anchor_age BETWEEN 68 AND 78
      AND a.admittime IS NOT NULL
      AND a.dischtime IS NOT NULL
      AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_pneumonia
        WHERE
          a.hadm_id = d_pneumonia.hadm_id
          AND (
            (d_pneumonia.icd_version = 9 AND SUBSTR(d_pneumonia.icd_code, 1, 3) BETWEEN '480' AND '486')
            OR (d_pneumonia.icd_version = 10 AND SUBSTR(d_pneumonia.icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
          )
      )
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d_copd
        WHERE
          a.hadm_id = d_copd.hadm_id
          AND (
            (d_copd.icd_version = 9 AND SUBSTR(d_copd.icd_code, 1, 3) BETWEEN '491' AND '496')
            OR (d_copd.icd_version = 10 AND d_copd.icd_code LIKE 'J44%')
          )
      )
  )
SELECT
  APPROX_QUANTILES(awd.length_of_stay_days, 100)[OFFSET(75)] AS p75_length_of_stay_days
FROM
  AdmissionsWithDiagnoses AS awd;
