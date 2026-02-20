WITH
  base_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 82 AND 92
  ),
  postop_cohort AS (
    SELECT DISTINCT
      b.hadm_id,
      b.admittime,
      b.dischtime,
      b.hospital_expire_flag
    FROM base_admissions AS b
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
      ON b.hadm_id = d.hadm_id
    WHERE
      (d.icd_version = 9 AND SUBSTR(d.icd_code, 1, 3) BETWEEN '996' AND '999')
      OR (d.icd_version = 10 AND SUBSTR(d.icd_code, 1, 2) = 'T8')
  ),
  comorbidity_counts AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT comorbidity_system) AS comorbidity_count
    FROM (
      SELECT
        hadm_id,
        CASE
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '428' THEN 'Heart Failure'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I50' THEN 'Heart Failure'
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '585' THEN 'CKD'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'N18' THEN 'CKD'
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '250' THEN 'Diabetes'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) BETWEEN 'E08' AND 'E13' THEN 'Diabetes'
          WHEN icd_version = 9 AND icd_code = '427.31' THEN 'AFib'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I48' THEN 'AFib'
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '401' THEN 'Hypertension'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I10' THEN 'Hypertension'
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) IN ('430', '431', '432', '433', '434') THEN 'Stroke'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) IN ('I60', 'I61', 'I62', 'I63') THEN 'Stroke'
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '486' THEN 'Pneumonia'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'J18' THEN 'Pneumonia'
          WHEN icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '584' THEN 'AKI'
          WHEN icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'N17' THEN 'AKI'
          ELSE NULL
        END AS comorbidity_system
      FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
      WHERE hadm_id IN (SELECT hadm_id FROM postop_cohort)
    )
    WHERE comorbidity_system IS NOT NULL
    GROUP BY hadm_id
  ),
  stratified_cohort AS (
    SELECT
      pc.hadm_id,
      pc.hospital_expire_flag,
      COALESCE(cc.comorbidity_count, 0) AS comorbidity_count,
      CASE
        WHEN EXISTS (
          SELECT 1 FROM `physionet-data.mimiciv_3_1_icu.icustays` icu
          WHERE icu.hadm_id = pc.hadm_id
        ) THEN 'ICU'
        ELSE 'Non-ICU'
      END AS icu_status,
      CASE
        WHEN DATETIME_DIFF(pc.dischtime, pc.admittime, DAY) <= 5 THEN '<=5 days'
        ELSE '>5 days'
      END AS los_bin,
      CASE
        WHEN COALESCE(cc.comorbidity_count, 0) <= 1 THEN '0-1'
        WHEN COALESCE(cc.comorbidity_count, 0) = 2 THEN '2'
        ELSE '>=3'
      END AS comorbidity_bin
    FROM postop_cohort AS pc
    LEFT JOIN comorbidity_counts AS cc
      ON pc.hadm_id = cc.hadm_id
  ),
  all_strata AS (
    SELECT
      icu_status,
      los_bin,
      comorbidity_bin
    FROM
      (SELECT icu_status FROM UNNEST(['ICU', 'Non-ICU']) AS icu_status)
      CROSS JOIN (SELECT los_bin FROM UNNEST(['<=5 days', '>5 days']) AS los_bin)
      CROSS JOIN (SELECT comorbidity_bin FROM UNNEST(['0-1', '2', '>=3']) AS comorbidity_bin)
  )
SELECT
  s.icu_status,
  s.los_bin,
  s.comorbidity_bin,
  COALESCE(COUNT(sc.hadm_id), 0) AS N,
  ROUND(SAFE_DIVIDE(SUM(sc.hospital_expire_flag), COUNT(sc.hadm_id)) * 100, 2) AS mortality_rate_pct,
  ROUND(AVG(sc.comorbidity_count), 2) AS avg_comorbidity_count
FROM all_strata AS s
LEFT JOIN stratified_cohort AS sc
  ON s.icu_status = sc.icu_status
  AND s.los_bin = sc.los_bin
  AND s.comorbidity_bin = sc.comorbidity_bin
GROUP BY
  s.icu_status,
  s.los_bin,
  s.comorbidity_bin
ORDER BY
  s.icu_status DESC,
  s.los_bin,
  CASE
    WHEN s.comorbidity_bin = '0-1' THEN 1
    WHEN s.comorbidity_bin = '2' THEN 2
    WHEN s.comorbidity_bin = '>=3' THEN 3
  END;
