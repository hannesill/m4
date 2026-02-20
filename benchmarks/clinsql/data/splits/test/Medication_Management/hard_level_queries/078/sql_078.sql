WITH
  base_patients AS (
    SELECT
      subject_id,
      anchor_age
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients`
    WHERE
      gender = 'F'
      AND anchor_age BETWEEN 74 AND 84
  ),
  pe_diagnoses AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 9 AND icd_code LIKE '4151%')
      OR (icd_version = 10 AND icd_code LIKE 'I26%')
    GROUP BY
      hadm_id
  ),
  pe_cohort_admissions AS (
    SELECT
      adm.hadm_id,
      adm.subject_id,
      adm.admittime,
      adm.dischtime,
      adm.hospital_expire_flag,
      bp.anchor_age
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
      INNER JOIN base_patients AS bp ON adm.subject_id = bp.subject_id
      INNER JOIN pe_diagnoses AS pe ON adm.hadm_id = pe.hadm_id
  ),
  first_24h_meds_pe AS (
    SELECT
      p.hadm_id,
      p.drug,
      p.route
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS p
      INNER JOIN pe_cohort_admissions AS adm ON p.hadm_id = adm.hadm_id
    WHERE
      DATETIME_DIFF(p.starttime, adm.admittime, HOUR) BETWEEN 0 AND 24
  ),
  pe_med_summary AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT drug) + COUNT(DISTINCT route) AS med_complexity_score,
      MAX(
        CASE
          WHEN LOWER(drug) LIKE '%amiodarone%' OR LOWER(drug) LIKE '%sotalol%' OR LOWER(drug) LIKE '%haloperidol%' OR LOWER(drug) LIKE '%ondansetron%' OR LOWER(drug) LIKE '%zofran%' OR LOWER(drug) LIKE '%ciprofloxacin%' OR LOWER(drug) LIKE '%levofloxacin%' OR LOWER(drug) LIKE '%azithromycin%' OR LOWER(drug) LIKE '%methadone%' THEN 1
          ELSE 0
        END
      ) AS has_qt_risk,
      MAX(
        CASE
          WHEN LOWER(drug) LIKE '%heparin%' OR LOWER(drug) LIKE '%warfarin%' OR LOWER(drug) LIKE '%coumadin%' OR LOWER(drug) LIKE '%enoxaparin%' OR LOWER(drug) LIKE '%lovenox%' OR LOWER(drug) LIKE '%apixaban%' OR LOWER(drug) LIKE '%eliquis%' OR LOWER(drug) LIKE '%rivaroxaban%' OR LOWER(drug) LIKE '%xarelto%' OR LOWER(drug) LIKE '%aspirin%' OR LOWER(drug) LIKE '%clopidogrel%' OR LOWER(drug) LIKE '%plavix%' OR LOWER(drug) LIKE '%ketorolac%' OR LOWER(drug) LIKE '%ibuprofen%' OR LOWER(drug) LIKE '%naproxen%' THEN 1
          ELSE 0
        END
      ) AS has_bleeding_risk
    FROM
      first_24h_meds_pe
    GROUP BY
      hadm_id
  ),
  pe_cohort_final_stats AS (
    SELECT
      adm.hadm_id,
      adm.subject_id,
      adm.anchor_age,
      COALESCE(ms.med_complexity_score, 0) AS med_complexity_score,
      COALESCE(ms.has_qt_risk, 0) AS has_qt_risk,
      COALESCE(ms.has_bleeding_risk, 0) AS has_bleeding_risk,
      adm.hospital_expire_flag,
      DATETIME_DIFF(adm.dischtime, adm.admittime, DAY) AS los_days,
      PERCENT_RANK() OVER (
        ORDER BY
          COALESCE(ms.med_complexity_score, 0)
      ) AS complexity_percentile_rank,
      NTILE(4) OVER (
        ORDER BY
          COALESCE(ms.med_complexity_score, 0) DESC
      ) AS complexity_quartile
    FROM
      pe_cohort_admissions AS adm
      LEFT JOIN pe_med_summary AS ms ON adm.hadm_id = ms.hadm_id
  ),
  icu_admissions AS (
    SELECT DISTINCT
      adm.hadm_id,
      adm.admittime
    FROM
      `physionet-data.mimiciv_3_1_icu.icustays` AS icu
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm ON icu.hadm_id = adm.hadm_id
  ),
  icu_med_summary AS (
    SELECT
      p.hadm_id,
      COUNT(DISTINCT p.drug) + COUNT(DISTINCT p.route) AS med_complexity_score,
      MAX(
        CASE
          WHEN LOWER(p.drug) LIKE '%amiodarone%' OR LOWER(p.drug) LIKE '%sotalol%' OR LOWER(p.drug) LIKE '%haloperidol%' OR LOWER(p.drug) LIKE '%ondansetron%' OR LOWER(p.drug) LIKE '%zofran%' OR LOWER(p.drug) LIKE '%ciprofloxacin%' OR LOWER(p.drug) LIKE '%levofloxacin%' OR LOWER(p.drug) LIKE '%azithromycin%' OR LOWER(p.drug) LIKE '%methadone%' THEN 1
          ELSE 0
        END
      ) AS has_qt_risk,
      MAX(
        CASE
          WHEN LOWER(p.drug) LIKE '%heparin%' OR LOWER(p.drug) LIKE '%warfarin%' OR LOWER(p.drug) LIKE '%coumadin%' OR LOWER(p.drug) LIKE '%enoxaparin%' OR LOWER(p.drug) LIKE '%lovenox%' OR LOWER(p.drug) LIKE '%apixaban%' OR LOWER(p.drug) LIKE '%eliquis%' OR LOWER(p.drug) LIKE '%rivaroxaban%' OR LOWER(p.drug) LIKE '%xarelto%' OR LOWER(p.drug) LIKE '%aspirin%' OR LOWER(p.drug) LIKE '%clopidogrel%' OR LOWER(p.drug) LIKE '%plavix%' OR LOWER(p.drug) LIKE '%ketorolac%' OR LOWER(p.drug) LIKE '%ibuprofen%' OR LOWER(p.drug) LIKE '%naproxen%' THEN 1
          ELSE 0
        END
      ) AS has_bleeding_risk
    FROM
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS p
      INNER JOIN icu_admissions AS adm ON p.hadm_id = adm.hadm_id
    WHERE
      DATETIME_DIFF(p.starttime, adm.admittime, HOUR) BETWEEN 0 AND 24
    GROUP BY
      p.hadm_id
  )
SELECT
  'Overall Complexity Distribution' AS metric,
  FORMAT(
    'Avg: %.2f, Min: %d, Max: %d, StdDev: %.2f',
    AVG(med_complexity_score),
    MIN(med_complexity_score),
    MAX(med_complexity_score),
    STDDEV(med_complexity_score)
  ) AS value,
  'Medication complexity score distribution for the target cohort.' AS description
FROM
  pe_cohort_final_stats
UNION ALL
SELECT
  'Interaction Risk Prevalence' AS metric,
  FORMAT(
    'QT Risk: %.1f%%, Bleeding Risk: %.1f%%',
    AVG(has_qt_risk) * 100,
    AVG(has_bleeding_risk) * 100
  ) AS value,
  'Percentage of patients in the cohort with potential drug interactions.' AS description
FROM
  pe_cohort_final_stats
UNION ALL
SELECT
  'Avg. Complexity Percentile by Risk' AS metric,
  FORMAT(
    'QT Risk Group: P%.1f, Bleeding Risk Group: P%.1f',
    AVG(
      CASE
        WHEN has_qt_risk = 1 THEN complexity_percentile_rank
        ELSE NULL
      END
    ) * 100,
    AVG(
      CASE
        WHEN has_bleeding_risk = 1 THEN complexity_percentile_rank
        ELSE NULL
      END
    ) * 100
  ) AS value,
  'Average complexity percentile rank for patients with specific interaction risks.' AS description
FROM
  pe_cohort_final_stats
UNION ALL
SELECT
  'Comparative Stats' AS metric,
  FORMAT(
    'Avg Complexity: %.2f, QT Risk: %.1f%%, Bleeding Risk: %.1f%%',
    AVG(med_complexity_score),
    AVG(has_qt_risk) * 100,
    AVG(has_bleeding_risk) * 100
  ) AS value,
  'Comparative metrics from a general population of ICU inpatients.' AS description
FROM
  icu_med_summary
UNION ALL
SELECT
  'Top Quartile (Complexity) Outcomes' AS metric,
  FORMAT(
    'Avg LOS: %.2f days, Mortality: %.1f%%',
    AVG(los_days),
    AVG(hospital_expire_flag) * 100
  ) AS value,
  'Clinical outcomes for patients in the highest 25% of medication complexity.' AS description
FROM
  pe_cohort_final_stats
WHERE
  complexity_quartile = 1;
