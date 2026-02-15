WITH
  pe_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age) BETWEEN 64 AND 74
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE d.hadm_id = a.hadm_id
          AND (
            (d.icd_version = 9 AND d.icd_code LIKE '4151%')
            OR (d.icd_version = 10 AND d.icd_code LIKE 'I26%')
          )
      )
  ),
  medication_complexity AS (
    SELECT
      c.hadm_id,
      COUNT(DISTINCT pr.drug) AS med_complexity_score
    FROM
      pe_cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON c.hadm_id = pr.hadm_id
    WHERE
      pr.starttime <= DATETIME_ADD(c.admittime, INTERVAL 24 HOUR)
    GROUP BY
      c.hadm_id
  ),
  outcomes AS (
    SELECT
      c.subject_id,
      c.hadm_id,
      c.hospital_expire_flag,
      GREATEST(0, DATETIME_DIFF(c.dischtime, c.admittime, DAY)) AS los_days,
      CASE
        WHEN DATETIME_DIFF(
          LEAD(c.admittime, 1) OVER (PARTITION BY c.subject_id ORDER BY c.admittime),
          c.dischtime,
          DAY
        ) <= 30 THEN 1
        ELSE 0
      END AS readmitted_30_days
    FROM
      pe_cohort AS c
  ),
  stratified_cohort AS (
    SELECT
      o.hadm_id,
      o.los_days,
      o.hospital_expire_flag,
      o.readmitted_30_days,
      COALESCE(mc.med_complexity_score, 0) AS med_complexity_score,
      NTILE(3) OVER (ORDER BY COALESCE(mc.med_complexity_score, 0)) AS complexity_tertile
    FROM
      outcomes AS o
    LEFT JOIN
      medication_complexity AS mc
      ON o.hadm_id = mc.hadm_id
  )
SELECT
  s.complexity_tertile,
  COUNT(s.hadm_id) AS num_admissions,
  MIN(s.med_complexity_score) AS min_med_score,
  MAX(s.med_complexity_score) AS max_med_score,
  ROUND(AVG(s.med_complexity_score), 2) AS avg_med_score,
  ROUND(AVG(s.los_days), 2) AS avg_los_days,
  ROUND(AVG(s.hospital_expire_flag) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(s.readmitted_30_days) * 100, 2) AS readmission_rate_30d_pct
FROM
  stratified_cohort AS s
GROUP BY
  s.complexity_tertile
ORDER BY
  s.complexity_tertile;
