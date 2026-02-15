WITH FirstDayAvgCreatinine AS (
  SELECT
    le.hadm_id,
    AVG(le.valuenum) AS avg_creatinine_24h
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` adm ON p.subject_id = adm.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` dx ON adm.hadm_id = dx.hadm_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` le ON adm.hadm_id = le.hadm_id
  WHERE
    p.gender = 'M'
    AND (
      (dx.icd_version = 9 AND (dx.icd_code LIKE '491%' OR dx.icd_code LIKE '492%' OR dx.icd_code LIKE '496%'))
      OR (dx.icd_version = 10 AND dx.icd_code LIKE 'J44%')
    )
    AND le.itemid = 50912
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 0.5 AND 10
    AND le.charttime BETWEEN adm.admittime AND TIMESTAMP_ADD(adm.admittime, INTERVAL 24 HOUR)
  GROUP BY
    le.hadm_id
)
SELECT
  ROUND(STDDEV(avg_creatinine_24h), 2) AS stddev_of_24h_avg_creatinine
FROM
  FirstDayAvgCreatinine;
