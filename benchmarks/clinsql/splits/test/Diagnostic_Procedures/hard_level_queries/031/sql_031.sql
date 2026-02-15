WITH
  hhs_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON a.hadm_id = d.hadm_id
    WHERE
      p.gender = 'M'
      AND (
        (d.icd_version = 9 AND d.icd_code LIKE '2502%')
        OR (d.icd_version = 10 AND (
          d.icd_code LIKE 'E100%'
          OR d.icd_code LIKE 'E110%'
          OR d.icd_code LIKE 'E130%'
          OR d.icd_code LIKE 'E140%'
        ))
      )
  ),
  hhs_icu_cohort AS (
    SELECT
      h.subject_id,
      h.hadm_id,
      i.stay_id,
      i.intime,
      h.admittime,
      h.dischtime,
      h.hospital_expire_flag
    FROM
      (SELECT DISTINCT subject_id, hadm_id, admittime, dischtime, hospital_expire_flag, age_at_admission FROM hhs_admissions) AS h
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS i
      ON h.hadm_id = i.hadm_id
    WHERE
      h.age_at_admission BETWEEN 66 AND 76
    QUALIFY ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) = 1
  ),
  procedures_in_window AS (
    SELECT
      pe.stay_id,
      COUNT(pe.itemid) AS procedure_count_48hr
    FROM
      `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
    INNER JOIN
      hhs_icu_cohort AS c
      ON pe.stay_id = c.stay_id
    WHERE
      pe.starttime BETWEEN c.intime AND DATETIME_ADD(c.intime, INTERVAL 48 HOUR)
    GROUP BY
      pe.stay_id
  ),
  readmission_flags AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(next_admittime, dischtime, DAY) <= 30 THEN 1
        ELSE 0
      END AS readmission_30d_flag
    FROM (
      SELECT
        hadm_id,
        subject_id,
        dischtime,
        LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
      FROM
        `physionet-data.mimiciv_3_1_hosp.admissions`
    )
  ),
  cohort_with_metrics AS (
    SELECT
      c.subject_id,
      c.hadm_id,
      c.stay_id,
      COALESCE(p.procedure_count_48hr, 0) AS procedure_count_48hr,
      c.hospital_expire_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, DAY) AS hospital_los_days,
      COALESCE(r.readmission_30d_flag, 0) AS readmission_30d_flag
    FROM
      hhs_icu_cohort AS c
    LEFT JOIN
      procedures_in_window AS p
      ON c.stay_id = p.stay_id
    LEFT JOIN
      readmission_flags AS r
      ON c.hadm_id = r.hadm_id
  ),
  cohort_with_ranks AS (
    SELECT
      *,
      NTILE(5) OVER (ORDER BY procedure_count_48hr) AS procedure_burden_quintile
    FROM
      cohort_with_metrics
  )
SELECT
  procedure_burden_quintile,
  COUNT(stay_id) AS num_icu_stays,
  ROUND(AVG(procedure_count_48hr), 2) AS avg_procedure_count,
  MIN(procedure_count_48hr) AS min_procedures_in_quintile,
  MAX(procedure_count_48hr) AS max_procedures_in_quintile,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(hospital_los_days), 1) AS avg_hospital_los_days,
  ROUND(AVG(CAST(readmission_30d_flag AS FLOAT64)) * 100, 2) AS readmission_rate_30d_percent
FROM
  cohort_with_ranks
GROUP BY
  procedure_burden_quintile
ORDER BY
  procedure_burden_quintile;
