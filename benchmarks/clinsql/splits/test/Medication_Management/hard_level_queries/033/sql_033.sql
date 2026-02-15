WITH
  sepsis_cohort AS (
    SELECT
      pat.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      (DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS pat
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      ON pat.subject_id = adm.subject_id
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON adm.hadm_id = dx.hadm_id
    WHERE
      pat.gender = 'M'
      AND (
        dx.icd_code LIKE '99591'
        OR dx.icd_code LIKE '99592'
        OR dx.icd_code LIKE '78552'
        OR dx.icd_code LIKE 'A41%'
        OR dx.icd_code LIKE 'R652%'
      )
      AND (DATETIME_DIFF(adm.admittime, DATETIME(pat.anchor_year, 1, 1, 0, 0, 0), YEAR) + pat.anchor_age) BETWEEN 80 AND 90
    GROUP BY
      pat.subject_id,
      adm.hadm_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      age_at_admission
  ),
  meds_first_24h AS (
    SELECT
      sc.hadm_id,
      LOWER(pr.drug) AS drug
    FROM
      sepsis_cohort AS sc
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON sc.hadm_id = pr.hadm_id
    WHERE
      pr.starttime BETWEEN sc.admittime AND DATETIME_ADD(sc.admittime, INTERVAL 24 HOUR)
  ),
  patient_med_summary AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT drug) AS med_complexity_score,
      COUNTIF(
        drug LIKE '%amiodarone%' OR drug LIKE '%ciprofloxacin%' OR drug LIKE '%levofloxacin%' OR
        drug LIKE '%azithromycin%' OR drug LIKE '%erythromycin%' OR drug LIKE '%haloperidol%' OR
        drug LIKE '%ondansetron%' OR drug LIKE '%sotalol%' OR drug LIKE '%methadone%' OR
        drug LIKE '%fluconazole%' OR drug LIKE '%quetiapine%' OR drug LIKE '%ziprasidone%'
      ) > 0 AS has_qt_risk,
      COUNTIF(
        drug LIKE '%warfarin%' OR drug LIKE '%heparin%' OR drug LIKE '%enoxaparin%' OR
        drug LIKE '%fondaparinux%' OR drug LIKE '%apixaban%' OR drug LIKE '%rivaroxaban%' OR
        drug LIKE '%dabigatran%' OR drug LIKE '%aspirin%' OR drug LIKE '%clopidogrel%' OR
        drug LIKE '%prasugrel%' OR drug LIKE '%ticagrelor%' OR drug LIKE '%ketorolac%' OR
        drug LIKE '%ibuprofen%' OR drug LIKE '%naproxen%'
      ) > 0 AS has_bleeding_risk
    FROM
      meds_first_24h
    GROUP BY
      hadm_id
  ),
  ranked_patients AS (
    SELECT
      sc.hadm_id,
      sc.hospital_expire_flag,
      CASE
        WHEN pms.has_qt_risk AND pms.has_bleeding_risk THEN 'QT_and_Bleeding_Risk'
        ELSE 'Matched_Cohort'
      END AS interaction_group,
      pms.med_complexity_score,
      DATETIME_DIFF(sc.dischtime, sc.admittime, DAY) AS los_days,
      PERCENT_RANK() OVER (ORDER BY pms.med_complexity_score) AS overall_complexity_percentile_rank,
      NTILE(4) OVER (ORDER BY pms.med_complexity_score) AS complexity_quartile
    FROM
      sepsis_cohort AS sc
    INNER JOIN
      patient_med_summary AS pms
      ON sc.hadm_id = pms.hadm_id
  )
SELECT
  interaction_group,
  COUNT(hadm_id) AS number_of_patients,
  ROUND(AVG(med_complexity_score), 2) AS avg_med_complexity_score,
  APPROX_QUANTILES(med_complexity_score, 100)[OFFSET(25)] AS p25_med_complexity_score,
  APPROX_QUANTILES(med_complexity_score, 100)[OFFSET(50)] AS p50_med_complexity_score,
  APPROX_QUANTILES(med_complexity_score, 100)[OFFSET(75)] AS p75_med_complexity_score,
  ROUND(AVG(overall_complexity_percentile_rank), 3) AS avg_overall_complexity_percentile,
  ROUND(AVG(los_days), 2) AS avg_los_days_all,
  ROUND(AVG(CAST(hospital_expire_flag AS INT64)), 3) AS mortality_rate_all,
  COUNTIF(complexity_quartile = 4) AS patients_in_top_quartile,
  ROUND(AVG(IF(complexity_quartile = 4, los_days, NULL)), 2) AS avg_los_days_top_quartile,
  ROUND(AVG(IF(complexity_quartile = 4, CAST(hospital_expire_flag AS INT64), NULL)), 3) AS mortality_rate_top_quartile
FROM
  ranked_patients
GROUP BY
  interaction_group
ORDER BY
  interaction_group DESC;
