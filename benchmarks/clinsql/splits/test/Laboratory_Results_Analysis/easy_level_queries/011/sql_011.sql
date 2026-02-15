WITH PeakPotassiumPerICUStay AS (
  SELECT
    i.stay_id,
    MAX(le.valuenum) AS peak_potassium
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
  JOIN
    `physionet-data.mimiciv_3_1_icu.icustays` AS i
    ON p.subject_id = i.subject_id
  JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON i.hadm_id = le.hadm_id
  WHERE
    p.gender = 'M'
    AND le.itemid = 50971
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 2.5 AND 8.0
    AND le.charttime BETWEEN i.intime AND i.outtime
  GROUP BY
    i.stay_id
)
SELECT
  ROUND(STDDEV(pk.peak_potassium), 2) AS stddev_peak_potassium
FROM
  PeakPotassiumPerICUStay AS pk;
