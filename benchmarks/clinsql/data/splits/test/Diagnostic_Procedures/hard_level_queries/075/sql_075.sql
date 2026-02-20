WITH
  dka_admissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND icd_code LIKE '2501%')
      OR (
        icd_version = 10 AND (
          icd_code LIKE 'E101%'
          OR icd_code LIKE 'E111%'
          OR icd_code LIKE 'E131%'
        )
      )
  ),
  first_icu_stays AS (
    SELECT
      icu.stay_id,
      icu.intime,
      icu.outtime,
      adm.hospital_expire_flag,
      ROW_NUMBER() OVER (PARTITION BY adm.hadm_id ORDER BY icu.intime) AS rn
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      ON adm.hadm_id = icu.hadm_id
    WHERE
      pat.gender = 'M'
      AND (pat.anchor_age + EXTRACT(YEAR FROM adm.admittime) - pat.anchor_year) BETWEEN 39 AND 49
      AND adm.hadm_id IN (SELECT hadm_id FROM dka_admissions)
  ),
  diagnostic_intensity AS (
    SELECT
      icu.stay_id,
      icu.intime,
      icu.outtime,
      icu.hospital_expire_flag,
      COUNT(DISTINCT pe.itemid) AS num_procedures_24h
    FROM first_icu_stays AS icu
    LEFT JOIN `physionet-data.mimiciv_3_1_icu.procedureevents` AS pe
      ON icu.stay_id = pe.stay_id
      AND pe.starttime BETWEEN icu.intime AND DATETIME_ADD(icu.intime, INTERVAL 24 HOUR)
    WHERE
      icu.rn = 1
    GROUP BY
      icu.stay_id,
      icu.intime,
      icu.outtime,
      icu.hospital_expire_flag
  ),
  intensity_quintiles AS (
    SELECT
      stay_id,
      intime,
      outtime,
      hospital_expire_flag,
      num_procedures_24h,
      NTILE(5) OVER (ORDER BY num_procedures_24h) AS diagnostic_quintile
    FROM diagnostic_intensity
  )
SELECT
  q.diagnostic_quintile,
  COUNT(q.stay_id) AS num_stays,
  AVG(q.num_procedures_24h) AS avg_procedure_count,
  MIN(q.num_procedures_24h) AS min_procedure_count,
  MAX(q.num_procedures_24h) AS max_procedure_count,
  AVG(DATETIME_DIFF(q.outtime, q.intime, HOUR) / 24.0) AS avg_icu_los_days,
  AVG(CAST(q.hospital_expire_flag AS FLOAT64)) * 100 AS hospital_mortality_percent
FROM intensity_quintiles AS q
GROUP BY
  q.diagnostic_quintile
ORDER BY
  q.diagnostic_quintile;
