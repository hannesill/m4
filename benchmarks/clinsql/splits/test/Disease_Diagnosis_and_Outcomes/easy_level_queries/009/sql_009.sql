WITH
  admissions_with_both_diagnoses AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
    HAVING
      SUM(
        CASE
          WHEN
            (
              icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'I20' AND 'I25'
            )
            OR (
              icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '410' AND '414'
            )
            THEN 1
          ELSE 0
        END
      ) > 0
      AND
      SUM(
        CASE
          WHEN
            (icd_version = 10 AND icd_code LIKE 'J44%')
            OR (
              icd_version = 9 AND SUBSTR(icd_code, 1, 3) BETWEEN '491' AND '496'
            )
            THEN 1
          ELSE 0
        END
      ) > 0
  )
SELECT
  ROUND(
    APPROX_QUANTILES(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY), 100)[OFFSET (75)],
    1
  ) AS p75_length_of_stay_days
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
  JOIN admissions_with_both_diagnoses AS d_cohort ON a.hadm_id = d_cohort.hadm_id
WHERE
  p.gender = 'M'
  AND p.anchor_age BETWEEN 75 AND 85
  AND a.dischtime IS NOT NULL
  AND a.admittime IS NOT NULL
  AND DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) >= 0;
