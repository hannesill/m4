WITH
  neutropenic_fever_admissions AS (
    SELECT
      hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    GROUP BY
      hadm_id
    HAVING
      COUNT(
        CASE
          WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 4) = '2880')
            OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'D70')
          THEN 1
        END
      ) > 0
      AND
      COUNT(
        CASE
          WHEN (icd_version = 9 AND SUBSTR(icd_code, 1, 4) = '7806')
            OR (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'R50')
          THEN 1
        END
      ) > 0
  ),

  cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      a.admittime,
      a.dischtime,
      a.hospital_expire_flag
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    INNER JOIN
      neutropenic_fever_admissions AS nfa
      ON a.hadm_id = nfa.hadm_id
    WHERE
      p.gender = 'F'
      AND (EXTRACT(YEAR FROM a.admittime) - p.anchor_year + p.anchor_age) BETWEEN 40 AND 50
  ),

  readmission_flags AS (
    SELECT
      hadm_id,
      CASE
        WHEN DATETIME_DIFF(
          LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime),
          dischtime,
          DAY
        ) <= 30 THEN 1
        ELSE 0
      END AS is_readmitted_30d
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
  ),

  meds_first_48h AS (
    SELECT
      c.hadm_id,
      pr.drug,
      pr.route
    FROM
      cohort AS c
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.prescriptions` AS pr
      ON c.hadm_id = pr.hadm_id
    WHERE
      pr.starttime BETWEEN c.admittime AND DATETIME_ADD(c.admittime, INTERVAL 48 HOUR)
  ),

  med_complexity_score AS (
    SELECT
      hadm_id,
      (
        (COUNT(DISTINCT drug) * 1.5) + (COUNT(DISTINCT route) * 1.0) + (
          SUM(
            CASE
              WHEN LOWER(drug) LIKE 'norepinephrine%'
                OR LOWER(drug) LIKE 'epinephrine%'
                OR LOWER(drug) LIKE 'vasopressin%'
                OR LOWER(drug) LIKE 'dopamine%'
                OR LOWER(drug) LIKE 'phenylephrine%'
                OR LOWER(drug) LIKE 'meropenem%'
                OR LOWER(drug) LIKE 'imipenem%'
                OR LOWER(drug) LIKE 'piperacillin%'
                OR LOWER(drug) LIKE 'cefepime%'
                OR LOWER(drug) LIKE 'vancomycin%'
                OR LOWER(drug) LIKE 'amphotericin%'
                OR LOWER(drug) LIKE 'voriconazole%'
                OR LOWER(drug) LIKE 'caspofungin%'
              THEN 1
              ELSE 0
            END
          ) * 2.0
        )
      ) AS medication_complexity_score
    FROM
      meds_first_48h
    GROUP BY
      hadm_id
  ),

  cohort_outcomes AS (
    SELECT
      c.hadm_id,
      c.hospital_expire_flag AS mortality_flag,
      DATETIME_DIFF(c.dischtime, c.admittime, HOUR) / 24.0 AS los_days,
      COALESCE(mcs.medication_complexity_score, 0) AS medication_complexity_score,
      COALESCE(rf.is_readmitted_30d, 0) AS is_readmitted_30d
    FROM
      cohort AS c
    LEFT JOIN
      med_complexity_score AS mcs
      ON c.hadm_id = mcs.hadm_id
    LEFT JOIN
      readmission_flags AS rf
      ON c.hadm_id = rf.hadm_id
  ),

  cohort_quartiles AS (
    SELECT
      hadm_id,
      los_days,
      mortality_flag,
      is_readmitted_30d,
      medication_complexity_score,
      NTILE(4) OVER (
        ORDER BY
          medication_complexity_score
      ) AS complexity_quartile
    FROM
      cohort_outcomes
  )

SELECT
  complexity_quartile,
  COUNT(hadm_id) AS num_patients,
  ROUND(AVG(medication_complexity_score), 2) AS avg_complexity_score,
  ROUND(MIN(medication_complexity_score), 2) AS min_complexity_score,
  ROUND(MAX(medication_complexity_score), 2) AS max_complexity_score,
  ROUND(AVG(los_days), 2) AS avg_los_days,
  ROUND(AVG(mortality_flag) * 100, 2) AS mortality_rate_percent,
  ROUND(AVG(is_readmitted_30d) * 100, 2) AS readmission_rate_30d_percent
FROM
  cohort_quartiles
GROUP BY
  complexity_quartile
ORDER BY
  complexity_quartile;
