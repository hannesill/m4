WITH
  ich_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      (EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year) + p.anchor_age BETWEEN 87 AND 97
      AND a.hadm_id IN (
        SELECT DISTINCT hadm_id
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
        WHERE
          (icd_version = 9 AND (
            icd_code LIKE '430%'
            OR icd_code LIKE '431%'
            OR icd_code LIKE '432%'
          ))
          OR (icd_version = 10 AND (
            icd_code LIKE 'I60%'
            OR icd_code LIKE 'I61%'
            OR icd_code LIKE 'I62%'
          ))
      )
  ),
  meds_first_48h AS (
    SELECT
      pr.hadm_id,
      pr.drug,
      pr.route
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
    JOIN
      ich_cohort AS ic
      ON pr.hadm_id = ic.hadm_id
    WHERE
      pr.starttime <= DATETIME_ADD(ic.admittime, INTERVAL 48 HOUR)
  ),
  complexity_scores AS (
    SELECT
      hadm_id,
      (COUNT(DISTINCT drug) + COUNT(DISTINCT route)) AS med_complexity_score
    FROM
      meds_first_48h
    GROUP BY
      hadm_id
  ),
  readmission_data AS (
    SELECT
      a.hadm_id,
      a.dischtime,
      LEAD(a.admittime, 1) OVER (PARTITION BY a.subject_id ORDER BY a.admittime) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    WHERE a.subject_id IN (SELECT DISTINCT subject_id FROM ich_cohort)
  ),
  patient_outcomes AS (
    SELECT
      ic.hadm_id,
      ic.hospital_expire_flag,
      CEIL(DATETIME_DIFF(ic.dischtime, ic.admittime, HOUR) / 24) AS los_days,
      CASE
        WHEN DATETIME_DIFF(rd.next_admittime, ic.dischtime, DAY) BETWEEN 0 AND 30 THEN 1
        ELSE 0
      END AS readmitted_30_days,
      COALESCE(cs.med_complexity_score, 0) AS med_complexity_score
    FROM
      ich_cohort AS ic
    LEFT JOIN
      complexity_scores AS cs
      ON ic.hadm_id = cs.hadm_id
    LEFT JOIN
      readmission_data AS rd
      ON ic.hadm_id = rd.hadm_id
  ),
  stratified_data AS (
    SELECT
      *,
      NTILE(4) OVER (ORDER BY med_complexity_score) AS complexity_quartile
    FROM
      patient_outcomes
  )
SELECT
  complexity_quartile,
  COUNT(hadm_id) AS num_admissions,
  MIN(med_complexity_score) AS min_complexity_score,
  MAX(med_complexity_score) AS max_complexity_score,
  ROUND(AVG(med_complexity_score), 2) AS avg_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(readmitted_30_days) * 100, 2) AS readmission_rate_30d_pct
FROM
  stratified_data
GROUP BY
  complexity_quartile
ORDER BY
  complexity_quartile;
