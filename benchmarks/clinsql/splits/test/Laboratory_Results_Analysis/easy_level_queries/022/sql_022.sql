WITH PeakPHPerICUStay AS (
  SELECT
    icu.stay_id,
    MAX(le.valuenum) AS peak_ph
  FROM
    `physionet-data.mimiciv_3_1_icu.icustays` AS icu
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.patients` AS p
    ON icu.subject_id = p.subject_id
  INNER JOIN
    `physionet-data.mimiciv_3_1_hosp.labevents` AS le
    ON icu.subject_id = le.subject_id AND icu.hadm_id = le.hadm_id
  WHERE
    p.gender = 'M'
    AND le.itemid = 50820
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 6.8 AND 7.8
  GROUP BY
    icu.stay_id
)
SELECT
  ROUND(
    (APPROX_QUANTILES(peak_ph, 4)[OFFSET(3)] - APPROX_QUANTILES(peak_ph, 4)[OFFSET(1)]),
    3
  ) AS iqr_peak_arterial_ph
FROM
  PeakPHPerICUStay;
