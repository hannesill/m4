WITH
  admission_sequences AS (
    SELECT
      hadm_id,
      subject_id,
      dischtime,
      LEAD(admittime, 1) OVER (PARTITION BY subject_id ORDER BY admittime) AS next_admittime
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions`
    WHERE
      dischtime IS NOT NULL
  ),
  index_aki_admissions AS (
    SELECT DISTINCT
      a.hadm_id
    FROM
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS p
      ON a.subject_id = p.subject_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
      ON a.hadm_id = dx.hadm_id
    WHERE
      p.gender = 'F'
      AND p.anchor_age BETWEEN 52 AND 62
      AND dx.icd_code IN (
        '5845', '5846', '5847', '5848', '5849',
        'N170', 'N171', 'N172', 'N179'
      )
  )
SELECT
  STDDEV_SAMP(
    CASE
      WHEN DATE_DIFF(DATE(seq.next_admittime), DATE(seq.dischtime), DAY) <= 30 THEN 1
      ELSE 0
    END
  ) AS stddev_30day_readmission_outcome
FROM
  admission_sequences AS seq
INNER JOIN index_aki_admissions AS idx
  ON seq.hadm_id = idx.hadm_id;
