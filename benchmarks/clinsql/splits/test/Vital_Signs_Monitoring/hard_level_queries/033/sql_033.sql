WITH
icustay_cohort AS (
    SELECT * FROM (
        SELECT
            icu.stay_id,
            icu.subject_id,
            icu.hadm_id,
            icu.intime,
            icu.outtime,
            adm.hospital_expire_flag,
            ROW_NUMBER() OVER(PARTITION BY icu.hadm_id ORDER BY icu.intime ASC) as icu_stay_rank
        FROM `physionet-data.mimiciv_3_1_icu.icustays` AS icu
        INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` AS pat
            ON icu.subject_id = pat.subject_id
        INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS adm
            ON icu.hadm_id = adm.hadm_id
        WHERE
            pat.gender = 'F'
            AND pat.anchor_age BETWEEN 51 AND 61
    )
    WHERE icu_stay_rank = 1
),
ventilation_events AS (
    SELECT DISTINCT ce.stay_id
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    WHERE ce.stay_id IN (SELECT stay_id FROM icustay_cohort)
      AND ce.itemid IN (
            224685,
            223849,
            720,
            223848
      )
      AND ce.charttime <= DATETIME_ADD((SELECT intime FROM icustay_cohort i WHERE i.stay_id = ce.stay_id), INTERVAL 48 HOUR)
),
ventilated_cohort AS (
    SELECT cohort.*
    FROM icustay_cohort AS cohort
    INNER JOIN ventilation_events AS vent
        ON cohort.stay_id = vent.stay_id
),
vitals_raw AS (
    SELECT
        vc.stay_id,
        ce.itemid,
        ce.valuenum
    FROM `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
    INNER JOIN ventilated_cohort AS vc
        ON ce.stay_id = vc.stay_id
    WHERE
        ce.charttime BETWEEN vc.intime AND DATETIME_ADD(vc.intime, INTERVAL 48 HOUR)
        AND ce.valuenum IS NOT NULL
        AND ce.itemid IN (
            220045,
            220277,
            220179,
            220050,
            220210,
            223762,
            223761
        )
),
vitals_abnormal AS (
    SELECT
        stay_id,
        CASE
            WHEN itemid = 220045 AND (valuenum < 50 OR valuenum > 120) THEN 1
            WHEN itemid = 220277 AND valuenum < 90 THEN 1
            WHEN itemid IN (220179, 220050) AND (valuenum < 90 OR valuenum > 180) THEN 1
            WHEN itemid = 220210 AND (valuenum < 8 OR valuenum > 30) THEN 1
            WHEN itemid = 223762 AND (valuenum < 36 OR valuenum > 38.5) THEN 1
            WHEN itemid = 223761 AND (((valuenum - 32) * 5 / 9) < 36 OR ((valuenum - 32) * 5 / 9) > 38.5) THEN 1
            ELSE 0
        END AS is_abnormal
    FROM vitals_raw
    WHERE
        (itemid = 220045 AND valuenum BETWEEN 1 AND 300)
        OR (itemid = 220277 AND valuenum BETWEEN 1 AND 100)
        OR (itemid IN (220179, 220050) AND valuenum BETWEEN 1 AND 300)
        OR (itemid = 220210 AND valuenum BETWEEN 1 AND 80)
        OR (itemid = 223762 AND valuenum BETWEEN 25 AND 45)
        OR (itemid = 223761 AND valuenum BETWEEN 70 AND 115)
),
instability_scores AS (
    SELECT
        vc.stay_id,
        vc.hospital_expire_flag,
        DATETIME_DIFF(vc.outtime, vc.intime, HOUR) AS icu_los_hours,
        COALESCE(SUM(va.is_abnormal), 0) AS instability_score
    FROM ventilated_cohort AS vc
    LEFT JOIN vitals_abnormal AS va
        ON vc.stay_id = va.stay_id
    GROUP BY
        vc.stay_id,
        vc.hospital_expire_flag,
        icu_los_hours
),
ranked_scores AS (
    SELECT
        s.*,
        NTILE(10) OVER (ORDER BY s.instability_score DESC) AS instability_decile
    FROM instability_scores AS s
)
SELECT
    SAFE_DIVIDE(
        COUNTIF(instability_score <= 80),
        COUNT(stay_id)
    ) * 100 AS percentile_rank_of_score_80,
    COUNT(stay_id) AS cohort_total_patients,
    COUNTIF(instability_decile = 1) AS top_decile_patient_count,
    AVG(IF(instability_decile = 1, icu_los_hours, NULL)) AS top_decile_avg_icu_los_hours,
    AVG(IF(instability_decile = 1, CAST(hospital_expire_flag AS FLOAT64), NULL)) * 100 AS top_decile_mortality_rate_percent
FROM ranked_scores;
