WITH FirstAdmissionLOS AS (
  SELECT
    DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY) AS length_of_stay
  FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
  JOIN
    `physionet-data.mimiciv_3_1_hosp.admissions` a ON p.subject_id = a.subject_id
  WHERE
    p.gender = 'F'
    AND p.anchor_age BETWEEN 77 AND 87
    AND a.admittime IS NOT NULL
    AND a.dischtime IS NOT NULL
  QUALIFY ROW_NUMBER() OVER(PARTITION BY p.subject_id ORDER BY a.admittime ASC) = 1
)
SELECT
  (APPROX_QUANTILES(length_of_stay, 4)[OFFSET(3)]) - (APPROX_QUANTILES(length_of_stay, 4)[OFFSET(1)]) AS iqr_length_of_stay
FROM
  FirstAdmissionLOS
WHERE
  length_of_stay >= 0;
