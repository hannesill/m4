WITH
  base_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.discharge_location,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'M'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 53 AND 63
      AND a.dischtime IS NOT NULL AND a.admittime IS NOT NULL
      AND EXISTS (
        SELECT 1
        FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
        WHERE d.hadm_id = a.hadm_id
        AND (
          d.icd_code LIKE '428%'
          OR d.icd_code LIKE 'I50%'
        )
      )
  ),
  charlson_components AS (
    SELECT
      d.hadm_id,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^410|^412') OR REGEXP_CONTAINS(d.icd_code, r'^I21|^I22|^I252') THEN 1 ELSE 0 END) AS mi,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^428') OR REGEXP_CONTAINS(d.icd_code, r'^I50|^I110|^I130|^I132') THEN 1 ELSE 0 END) AS chf,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^441|^4439|^7854|^V434') OR REGEXP_CONTAINS(d.icd_code, r'^I71|^I739|^I70') THEN 1 ELSE 0 END) AS pvd,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^43[0-8]') OR REGEXP_CONTAINS(d.icd_code, r'^I6[0-9]|^G45') THEN 1 ELSE 0 END) AS cva,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^290|^2941|^3312') OR REGEXP_CONTAINS(d.icd_code, r'^F0[0-3]|^F051|^G30|^G311') THEN 1 ELSE 0 END) AS dementia,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^49[0-6]|^50[0-5]|^5064') OR REGEXP_CONTAINS(d.icd_code, r'^J4[0-7]|^J6[0-7]') THEN 1 ELSE 0 END) AS cpd,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^710[014]|^714[0-2]|^7148|^725') OR REGEXP_CONTAINS(d.icd_code, r'^M05|^M06|^M32|^M33|^M34') THEN 1 ELSE 0 END) AS rheum,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^53[1-4]') OR REGEXP_CONTAINS(d.icd_code, r'^K2[5-8]') THEN 1 ELSE 0 END) AS pud,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^571[2456]') OR REGEXP_CONTAINS(d.icd_code, r'^B18|^K70[0-3]|^K709|^K71[3-5]|^K717|^K73|^K74|^K760') THEN 1 ELSE 0 END) AS mild_liver,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^250[0-389]') OR REGEXP_CONTAINS(d.icd_code, r'^E1[01234][01689]') THEN 1 ELSE 0 END) AS diab_uncomp,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^250[4-7]') OR REGEXP_CONTAINS(d.icd_code, r'^E1[01234][2-57]') THEN 1 ELSE 0 END) AS diab_comp,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^3441|^342') OR REGEXP_CONTAINS(d.icd_code, r'^G81|^G82|^G041') THEN 1 ELSE 0 END) AS paraplegia,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^582|^583|^585|^586|^V420|^V451|^V56') OR REGEXP_CONTAINS(d.icd_code, r'^I120|^I131|^N18|^N19|^N250|^Z49[0-2]|^Z992|^Z940') THEN 1 ELSE 0 END) AS renal,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^(1[4-9][0-9])|(20[0-8])') AND NOT REGEXP_CONTAINS(d.icd_code, r'^19[6-9]') OR REGEXP_CONTAINS(d.icd_code, r'^C[0-7][0-9]|^C8[1-9]|^C9[0-7]') AND NOT REGEXP_CONTAINS(d.icd_code, r'^C7[7-9]|^C80') THEN 1 ELSE 0 END) AS malignancy,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^456[0-2]|^572[2-8]') OR REGEXP_CONTAINS(d.icd_code, r'^I85[09]|^I864|^I982|^K704|^K711|^K72|^K76[5-7]') THEN 1 ELSE 0 END) AS severe_liver,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^19[6-9]') OR REGEXP_CONTAINS(d.icd_code, r'^C7[7-9]|^C80') THEN 1 ELSE 0 END) AS mets,
      MAX(CASE WHEN REGEXP_CONTAINS(d.icd_code, r'^04[2-4]') OR REGEXP_CONTAINS(d.icd_code, r'^B2[0-4]') THEN 1 ELSE 0 END) AS aids
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS d
    WHERE d.hadm_id IN (SELECT hadm_id FROM base_cohort)
    GROUP BY
      d.hadm_id
  ),
  charlson_scores AS (
    SELECT
      hadm_id,
      (mi * 1) + (chf * 1) + (pvd * 1) + (cva * 1) + (dementia * 1) + (cpd * 1) + (rheum * 1) + (pud * 1)
      + (mild_liver * 1) + (diab_uncomp * 1)
      + (diab_comp * 2) + (paraplegia * 2) + (renal * 2) + (malignancy * 2)
      + (severe_liver * 3)
      + (mets * 6) + (aids * 6)
      AS charlson_index
    FROM
      charlson_components
  ),
  cohort_stratified AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag,
      CASE
        WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) <= 3 THEN '1-3 days'
        WHEN DATETIME_DIFF(c.dischtime, c.admittime, DAY) BETWEEN 4 AND 7 THEN '4-7 days'
        ELSE '>=8 days'
      END AS los_group,
      CASE
        WHEN cs.charlson_index <= 3 THEN '<=3'
        WHEN cs.charlson_index BETWEEN 4 AND 5 THEN '4-5'
        ELSE '>5'
      END AS charlson_group,
      CASE
        WHEN c.discharge_location IN ('HOME', 'HOME HEALTH CARE') THEN 'Home'
        WHEN c.discharge_location = 'REHAB/DISTINCT PART HOSP' THEN 'Rehab'
        WHEN c.discharge_location = 'SKILLED NURSING FACILITY' THEN 'SNF'
        WHEN c.discharge_location = 'HOSPICE' THEN 'Hospice'
        ELSE 'Other/Expired'
      END AS discharge_category
    FROM
      base_cohort AS c
    INNER JOIN
      charlson_scores AS cs
      ON c.hadm_id = cs.hadm_id
  ),
  aggregated_stats AS (
    SELECT
      charlson_group,
      los_group,
      CASE
        WHEN los_group = '1-3 days' THEN 1
        WHEN los_group = '4-7 days' THEN 2
        ELSE 3
      END AS los_sort_order,
      COUNT(*) AS total_patients,
      SUM(hospital_expire_flag) AS total_deaths,
      ROUND(100.0 * SUM(hospital_expire_flag) / COUNT(*), 2) AS mortality_rate_pct,
      SUM(CASE WHEN discharge_category = 'Home' THEN 1 ELSE 0 END) AS discharge_home,
      SUM(CASE WHEN discharge_category = 'Rehab' THEN 1 ELSE 0 END) AS discharge_rehab,
      SUM(CASE WHEN discharge_category = 'SNF' THEN 1 ELSE 0 END) AS discharge_snf,
      SUM(CASE WHEN discharge_category = 'Hospice' THEN 1 ELSE 0 END) AS discharge_hospice
    FROM
      cohort_stratified
    GROUP BY
      charlson_group,
      los_group
  )
SELECT
  s.charlson_group,
  s.los_group,
  s.total_patients,
  s.total_deaths,
  s.mortality_rate_pct,
  LAG(s.mortality_rate_pct, 1, 0) OVER (PARTITION BY s.charlson_group ORDER BY s.los_sort_order) AS prev_los_group_mortality_pct,
  ROUND(s.mortality_rate_pct - LAG(s.mortality_rate_pct, 1, 0) OVER (PARTITION BY s.charlson_group ORDER BY s.los_sort_order), 2) AS abs_mortality_diff_vs_prev_los_group,
  ROUND(
    SAFE_DIVIDE(
      s.mortality_rate_pct - LAG(s.mortality_rate_pct, 1, 0) OVER (PARTITION BY s.charlson_group ORDER BY s.los_sort_order),
      LAG(s.mortality_rate_pct, 1, 0) OVER (PARTITION BY s.charlson_group ORDER BY s.los_sort_order)
    ) * 100, 2
  ) AS rel_mortality_diff_pct_vs_prev_los_group,
  ROUND(100.0 * s.discharge_home / s.total_patients, 1) AS discharge_home_pct,
  ROUND(100.0 * s.discharge_rehab / s.total_patients, 1) AS discharge_rehab_pct,
  ROUND(100.0 * s.discharge_snf / s.total_patients, 1) AS discharge_snf_pct,
  ROUND(100.0 * s.discharge_hospice / s.total_patients, 1) AS discharge_hospice_pct
FROM
  aggregated_stats AS s
ORDER BY
  CASE
    WHEN s.charlson_group = '<=3' THEN 1
    WHEN s.charlson_group = '4-5' THEN 2
    ELSE 3
  END,
  s.los_sort_order;
