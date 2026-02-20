WITH first_icu_sodium AS (
    SELECT
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime) as rn
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.labevents` le ON p.subject_id = le.subject_id
    JOIN
        `physionet-data.mimiciv_3_1_icu.icustays` icu ON le.hadm_id = icu.hadm_id
    WHERE
        p.gender = 'M'
        AND le.itemid = 50983
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 120 AND 160
),
quartiles AS (
    SELECT
        APPROX_QUANTILES(valuenum, 4) as sodium_quantiles
    FROM
        first_icu_sodium
    WHERE
        rn = 1
)
SELECT
    ROUND(sodium_quantiles[OFFSET(3)] - sodium_quantiles[OFFSET(1)], 2) as iqr_serum_sodium
FROM
    quartiles;
