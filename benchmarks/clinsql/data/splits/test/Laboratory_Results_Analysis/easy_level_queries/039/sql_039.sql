WITH PeakCreatininePerPneumoniaAdmission AS (
  SELECT
    MAX(le.valuenum) AS peak_creatinine
  FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` AS dx
    ON p.subject_id = dx.subject_id
  INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON dx.hadm_id = le.hadm_id
  WHERE
    p.gender = 'M'
    AND (
      (dx.icd_version = 9 AND SUBSTR(dx.icd_code, 1, 3) BETWEEN '480' AND '486') OR
      (dx.icd_version = 10 AND SUBSTR(dx.icd_code, 1, 3) BETWEEN 'J12' AND 'J18')
    )
    AND le.itemid = 50912
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 0.5 AND 10
  GROUP BY
    le.hadm_id
)
SELECT
  ROUND(STDDEV(peak_creatinine), 2) AS stddev_peak_creatinine
FROM PeakCreatininePerPneumoniaAdmission;
