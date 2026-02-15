WITH First24hHeartRates AS (
    SELECT
        ce.valuenum,
        ce.charttime,
        MIN(ce.charttime) OVER (PARTITION BY ce.stay_id) as first_hr_measurement_time
    FROM `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN `physionet-data.mimiciv_3_1_icu.chartevents` ce ON p.subject_id = ce.subject_id
    WHERE
        p.gender = 'F'
      AND p.anchor_age BETWEEN 44 AND 54
      AND ce.itemid IN (220045, 211)
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 30 AND 200
)
SELECT
    ROUND(MIN(fhr.valuenum), 2) as min_heart_rate
FROM First24hHeartRates fhr
WHERE
    fhr.charttime <= TIMESTAMP_ADD(fhr.first_hr_measurement_time, INTERVAL 24 HOUR);
