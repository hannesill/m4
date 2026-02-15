WITH patient_cohort AS (
    SELECT
        p.subject_id,
        ie.stay_id,
        ie.intime
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN
        `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie
        ON a.hadm_id = ie.hadm_id
    WHERE
        p.gender = 'F'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 45 AND 55
        AND ie.intime IS NOT NULL
),
first_24hr_sbp_measurements AS (
    SELECT
        pc.subject_id,
        pc.stay_id,
        ce.valuenum
    FROM
        patient_cohort AS pc
    INNER JOIN
        `physionet-data.mimiciv_3_1_icu.chartevents` AS ce
        ON pc.stay_id = ce.stay_id
    WHERE
        ce.itemid IN (
            220050,
            220179,
            51
        )
        AND ce.charttime BETWEEN pc.intime AND DATETIME_ADD(pc.intime, INTERVAL 24 HOUR)
        AND ce.valuenum IS NOT NULL
        AND ce.valuenum BETWEEN 40 AND 300
),
avg_sbp_per_stay AS (
    SELECT
        subject_id,
        stay_id,
        AVG(valuenum) AS average_sbp
    FROM
        first_24hr_sbp_measurements
    GROUP BY
        subject_id, stay_id
),
categorized_stays AS (
    SELECT
        subject_id,
        stay_id,
        CASE
            WHEN average_sbp < 140 THEN '< 140 mmHg'
            WHEN average_sbp >= 140 AND average_sbp < 160 THEN '140-159 mmHg'
            WHEN average_sbp >= 160 THEN '>= 160 mmHg'
            ELSE 'Unknown'
        END AS sbp_category
    FROM
        avg_sbp_per_stay
)
SELECT
    sbp_category,
    COUNT(DISTINCT subject_id) AS patient_count,
    ROUND(
        100.0 * COUNT(DISTINCT subject_id) / SUM(COUNT(DISTINCT subject_id)) OVER(),
        2
    ) AS percentage_of_patients
FROM
    categorized_stays
WHERE
    sbp_category != 'Unknown'
GROUP BY
    sbp_category
ORDER BY
    CASE
        WHEN sbp_category = '< 140 mmHg' THEN 1
        WHEN sbp_category = '140-159 mmHg' THEN 2
        WHEN sbp_category = '>= 160 mmHg' THEN 3
    END;
