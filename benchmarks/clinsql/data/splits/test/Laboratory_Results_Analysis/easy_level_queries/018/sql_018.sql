WITH FirstICUPh AS (
    SELECT
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY ie.stay_id ORDER BY le.charttime ASC) as rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` AS p
    JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` AS ie ON p.subject_id = ie.subject_id
    JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` AS le ON ie.hadm_id = le.hadm_id
    WHERE
        p.gender = 'F'
        AND le.itemid = 50820
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 7.0 AND 7.7
        AND le.charttime >= ie.intime AND le.charttime <= ie.outtime
)
SELECT
    ROUND(APPROX_QUANTILES(valuenum, 2)[OFFSET(1)], 2) AS median_admission_ph
FROM
    FirstICUPh
WHERE
    rn = 1
