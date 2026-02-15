SELECT
  MAX(DATE_DIFF(DATE(a.dischtime), DATE(a.admittime), DAY)) AS max_length_of_stay
FROM
  `physionet-data.mimiciv_3_1_hosp.patients` AS p
JOIN
  `physionet-data.mimiciv_3_1_hosp.admissions` AS a
  ON p.subject_id = a.subject_id
WHERE
  p.gender = 'M'
  AND p.anchor_age BETWEEN 58 AND 68
  AND a.dischtime IS NOT NULL
  AND a.admittime IS NOT NULL;
