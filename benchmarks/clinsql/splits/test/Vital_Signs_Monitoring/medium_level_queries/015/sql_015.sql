WITH
  ed_admissions AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
      `physionet-data.mimiciv_3_1_hosp.admissions` AS a
      ON p.subject_id = a.subject_id
    WHERE
      p.gender = 'F'
      AND a.admission_location = 'EMERGENCY ROOM'
  ),
  target_stays AS (
    SELECT
      ea.subject_id,
      ea.hadm_id,
      ie.stay_id
    FROM
      ed_admissions AS ea
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.icustays` AS ie
      ON ea.hadm_id = ie.hadm_id
    WHERE
      ea.age_at_admission BETWEEN 59 AND 69
      AND ie.stay_id IS NOT NULL
  ),
  max_sbp_per_stay AS (
    SELECT
      ts.stay_id,
      MAX(ce.valuenum) AS max_sbp
    FROM
      target_stays AS ts
    INNER JOIN
      `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
      ON ts.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220050, 51)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 40 AND 300
    GROUP BY
      ts.stay_id
  )
SELECT
  ROUND(APPROX_QUANTILES(max_sbp, 100)[OFFSET(75)], 2) AS p75_max_systolic_bp
FROM
  max_sbp_per_stay;
