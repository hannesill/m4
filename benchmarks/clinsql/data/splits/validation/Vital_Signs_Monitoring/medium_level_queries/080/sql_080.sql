WITH
  patient_cohort AS (
    SELECT
      p.subject_id,
      a.hadm_id,
      ie.stay_id,
      ie.intime,
      (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) AS age_at_admission
    FROM
      `physionet-data.mimiciv_3_1_hosp.patients` AS p
      INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a ON p.subject_id = a.subject_id
      INNER JOIN `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON a.hadm_id = ie.hadm_id
    WHERE
      p.gender = 'F'
      AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 56 AND 66
      AND ie.intime IS NOT NULL
  ),
  map_measurements_first_48h AS (
    SELECT
      pc.stay_id,
      ce.valuenum AS map_value
    FROM
      patient_cohort AS pc
      INNER JOIN `physionet-data.mimiciv_3_1_icu.chartevents` AS ce ON pc.stay_id = ce.stay_id
    WHERE
      ce.itemid IN (220052, 456, 224322, 52)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 20 AND 200
      AND ce.charttime BETWEEN pc.intime AND DATETIME_ADD(pc.intime, INTERVAL 48 HOUR)
  ),
  avg_map_per_stay AS (
    SELECT
      stay_id,
      AVG(map_value) AS avg_map
    FROM
      map_measurements_first_48h
    GROUP BY
      stay_id
  ),
  categorized_stays AS (
    SELECT
      stay_id,
      avg_map,
      CASE
        WHEN avg_map < 65 THEN '< 65 mmHg (Hypotensive)'
        WHEN avg_map >= 65 AND avg_map < 75 THEN '65-74 mmHg (Low Normal)'
        WHEN avg_map >= 75 AND avg_map < 85 THEN '75-84 mmHg (Normal)'
        WHEN avg_map >= 85 THEN '>= 85 mmHg (High)'
        ELSE 'Unknown'
      END AS map_category
    FROM
      avg_map_per_stay
  )
SELECT
  map_category,
  COUNT(stay_id) AS number_of_stays,
  ROUND(AVG(avg_map), 2) AS mean_of_stay_averages,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(50)], 2) AS median_of_stay_averages,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(25)], 2) AS p25_of_stay_averages,
  ROUND(APPROX_QUANTILES(avg_map, 100)[OFFSET(75)], 2) AS p75_of_stay_averages,
  ROUND(
    APPROX_QUANTILES(avg_map, 100)[OFFSET(75)] - APPROX_QUANTILES(avg_map, 100)[OFFSET(25)],
    2
  ) AS iqr_of_stay_averages
FROM
  categorized_stays
WHERE
  map_category != 'Unknown'
GROUP BY
  map_category
ORDER BY
  CASE
    WHEN map_category = '< 65 mmHg (Hypotensive)' THEN 1
    WHEN map_category = '65-74 mmHg (Low Normal)' THEN 2
    WHEN map_category = '75-84 mmHg (Normal)' THEN 3
    WHEN map_category = '>= 85 mmHg (High)' THEN 4
  END;
