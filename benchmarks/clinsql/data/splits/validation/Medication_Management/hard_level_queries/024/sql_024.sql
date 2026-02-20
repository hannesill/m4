WITH
  TraumaHadmIDs AS (
    SELECT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
      (icd_version = 10 AND SUBSTR(icd_code, 1, 1) IN ('S', 'T'))
      OR
      (icd_version = 9 AND (SUBSTR(icd_code, 1, 1) = '8' OR SUBSTR(icd_code, 1, 2) IN ('90', '91', '92', '95')))
    GROUP BY hadm_id
    HAVING COUNT(DISTINCT SUBSTR(icd_code, 1, 3)) >= 2
  ),
  PatientCohorts AS (
    SELECT
      a.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission,
      CASE
        WHEN p.gender = 'F' AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 68 AND 78
          THEN 'Target: Female 68-78 Multi-Trauma'
        ELSE 'Comparison: All Other Multi-Trauma'
      END AS cohort_name
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN TraumaHadmIDs AS t
      ON a.hadm_id = t.hadm_id
  ),
  PatientLevelStats AS (
    SELECT
      pc.hadm_id,
      pc.cohort_name,
      pc.los_days,
      pc.hospital_expire_flag,
      COUNT(DISTINCT pr.drug) AS medication_complexity_score,
      CASE
        WHEN COUNT(DISTINCT
          CASE
            WHEN LOWER(pr.drug) IN (
                'sertraline', 'zoloft', 'citalopram', 'celexa', 'escitalopram', 'lexapro',
                'fluoxetine', 'prozac', 'paroxetine', 'paxil', 'venlafaxine', 'effexor',
                'duloxetine', 'cymbalta', 'amitriptyline', 'nortriptyline', 'imipramine',
                'tramadol', 'ultram', 'fentanyl', 'sublimaze', 'duragesic', 'meperidine',
                'demerol', 'methadone', 'dolophine', 'ondansetron', 'zofran', 'linezolid',
                'zyvox', 'buspirone', 'buspar'
            ) OR LOWER(pr.drug) LIKE '%triptan%' THEN pr.drug
            ELSE NULL
          END
        ) >= 2 THEN 1
        ELSE 0
      END AS has_serotonergic_interaction
    FROM PatientCohorts AS pc
    LEFT JOIN `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON pc.hadm_id = pr.hadm_id
      AND pr.starttime BETWEEN pc.admittime AND DATETIME_ADD(pc.admittime, INTERVAL 24 HOUR)
    GROUP BY
      pc.hadm_id,
      pc.cohort_name,
      pc.los_days,
      pc.hospital_expire_flag
  ),
  RankedPatients AS (
    SELECT
      *,
      PERCENT_RANK() OVER(PARTITION BY cohort_name ORDER BY medication_complexity_score) AS complexity_percentile_rank,
      NTILE(4) OVER(PARTITION BY cohort_name ORDER BY medication_complexity_score DESC) AS complexity_quartile
    FROM PatientLevelStats
  )
SELECT
  cohort_name,
  CASE WHEN has_serotonergic_interaction = 1 THEN 'Interaction Risk Present' ELSE 'No Interaction Risk' END AS subgroup,
  COUNT(hadm_id) AS num_patients,
  APPROX_QUANTILES(medication_complexity_score, 4) AS complexity_score_quartiles,
  ROUND(AVG(complexity_percentile_rank) * 100, 1) AS avg_complexity_percentile,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent
FROM RankedPatients
GROUP BY
  cohort_name,
  has_serotonergic_interaction
UNION ALL
SELECT
  cohort_name,
  'Top 25% Complexity' AS subgroup,
  COUNT(hadm_id) AS num_patients,
  APPROX_QUANTILES(medication_complexity_score, 4) AS complexity_score_quartiles,
  NULL AS avg_complexity_percentile,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(CAST(hospital_expire_flag AS FLOAT64)) * 100, 2) AS mortality_rate_percent
FROM RankedPatients
WHERE
  complexity_quartile = 1
GROUP BY
  cohort_name
ORDER BY
  cohort_name,
  subgroup;
