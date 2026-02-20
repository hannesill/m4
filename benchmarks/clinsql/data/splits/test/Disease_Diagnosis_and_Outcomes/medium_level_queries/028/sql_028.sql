WITH
  base_cohort AS (
    SELECT
      a.hadm_id,
      a.hospital_expire_flag,
      DATETIME_DIFF(a.dischtime, a.admittime, DAY) AS los_days
    FROM `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 43 AND 53
      AND EXISTS (
        SELECT
          1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE
          d.hadm_id = a.hadm_id
          AND (
            d.icd_code LIKE '428%'
            OR d.icd_code LIKE 'I50%'
          )
      )
  ),
  comorbidity_counts AS (
    SELECT
      hadm_id,
      COUNT(DISTINCT icd_code) AS diag_count
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
  ),
  cohort_with_features AS (
    SELECT
      bc.hadm_id,
      bc.hospital_expire_flag,
      bc.los_days,
      cc.diag_count
    FROM base_cohort AS bc
    INNER JOIN comorbidity_counts AS cc
      ON bc.hadm_id = cc.hadm_id
  ),
  stratified_cohort AS (
    SELECT
      hadm_id,
      hospital_expire_flag,
      CASE
        WHEN NTILE(4) OVER (
          ORDER BY los_days
        ) = 1
        THEN 'Q1'
        WHEN NTILE(4) OVER (
          ORDER BY los_days
        ) = 2
        THEN 'Q2'
        WHEN NTILE(4) OVER (
          ORDER BY los_days
        ) = 3
        THEN 'Q3'
        WHEN NTILE(4) OVER (
          ORDER BY los_days
        ) = 4
        THEN 'Q4'
      END AS los_quartile,
      CASE
        WHEN NTILE(3) OVER (
          ORDER BY diag_count
        ) = 1
        THEN 'Low'
        WHEN NTILE(3) OVER (
          ORDER BY diag_count
        ) = 2
        THEN 'Medium'
        WHEN NTILE(3) OVER (
          ORDER BY diag_count
        ) = 3
        THEN 'High'
      END AS comorbidity_burden
    FROM cohort_with_features
  ),
  all_strata AS (
    SELECT
      los_quartile,
      comorbidity_burden
    FROM
      (
        SELECT los_quartile FROM UNNEST(['Q1', 'Q2', 'Q3', 'Q4']) AS los_quartile
      )
      CROSS JOIN (
        SELECT
          comorbidity_burden
        FROM
          UNNEST(['Low', 'Medium', 'High']) AS comorbidity_burden
      )
  )
SELECT
  g.comorbidity_burden,
  g.los_quartile,
  COUNT(s.hadm_id) AS number_of_admissions,
  ROUND(
    SAFE_DIVIDE(SUM(s.hospital_expire_flag), COUNT(s.hadm_id)) * 100,
    2
  ) AS mortality_rate_percent
FROM all_strata AS g
LEFT JOIN stratified_cohort AS s
  ON g.los_quartile = s.los_quartile AND g.comorbidity_burden = s.comorbidity_burden
GROUP BY
  g.comorbidity_burden,
  g.los_quartile
ORDER BY
  CASE g.comorbidity_burden
    WHEN 'Low'
    THEN 1
    WHEN 'Medium'
    THEN 2
    WHEN 'High'
    THEN 3
  END,
  g.los_quartile;
