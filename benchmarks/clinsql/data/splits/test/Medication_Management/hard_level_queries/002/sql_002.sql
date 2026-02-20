WITH
  ami_cohort AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    WHERE
      pat.gender = 'M'
      AND (DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age) BETWEEN 67 AND 77
      AND EXISTS (
        SELECT
          1
        FROM
          `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
        WHERE
          dx.hadm_id = adm.hadm_id
          AND (
            (dx.icd_version = 9 AND dx.icd_code LIKE '410%')
            OR (dx.icd_version = 10 AND dx.icd_code LIKE 'I21%')
          )
      )
  ),
  first_24h_prescriptions AS (
    SELECT
      presc.hadm_id,
      presc.drug,
      presc.route
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS presc
    INNER JOIN
      ami_cohort AS cohort
      ON presc.hadm_id = cohort.hadm_id
    WHERE
      presc.starttime <= DATETIME_ADD(cohort.admittime, INTERVAL 24 HOUR)
  ),
  medication_complexity AS (
    SELECT
      hadm_id,
      (
        (COUNT(DISTINCT LOWER(drug)) * 2)
        + (COUNT(DISTINCT route))
        + (COUNT(DISTINCT CASE WHEN LOWER(route) LIKE 'iv%' THEN LOWER(drug) END) * 3)
      ) AS medication_complexity_score
    FROM
      first_24h_prescriptions
    GROUP BY
      hadm_id
  ),
  readmission_data AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(
          LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime),
          dischtime,
          DAY
        ) <= 30 THEN 1
        ELSE 0
      END AS readmitted_within_30_days
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  ),
  cohort_with_tertiles AS (
    SELECT
      cohort.hadm_id,
      cohort.admittime,
      cohort.dischtime,
      cohort.hospital_expire_flag,
      COALESCE(mc.medication_complexity_score, 0) AS medication_complexity_score,
      COALESCE(rd.readmitted_within_30_days, 0) AS readmitted_within_30_days,
      NTILE(3) OVER (
        ORDER BY
          COALESCE(mc.medication_complexity_score, 0)
      ) AS complexity_tertile
    FROM
      ami_cohort AS cohort
    LEFT JOIN
      medication_complexity AS mc
      ON cohort.hadm_id = mc.hadm_id
    LEFT JOIN
      readmission_data AS rd
      ON cohort.hadm_id = rd.hadm_id
  )
SELECT
  complexity_tertile,
  COUNT(hadm_id) AS number_of_admissions,
  MIN(medication_complexity_score) AS min_complexity_score,
  MAX(medication_complexity_score) AS max_complexity_score,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(DATETIME_DIFF(dischtime, admittime, HOUR) / 24.0), 2) AS avg_length_of_stay_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS in_hospital_mortality_pct,
  ROUND(AVG(CAST(readmitted_within_30_days AS FLOAT64)) * 100, 2) AS readmission_30_day_pct
FROM
  cohort_with_tertiles
GROUP BY
  complexity_tertile
ORDER BY
  complexity_tertile;
