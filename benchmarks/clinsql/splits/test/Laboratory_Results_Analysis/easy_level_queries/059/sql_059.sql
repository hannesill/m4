WITH SepsisAdmissions AS (
    SELECT DISTINCT hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND icd_code IN ('99591', '99592'))
        OR
        (icd_version = 10 AND (icd_code LIKE 'A40%' OR icd_code LIKE 'A41%'))
),
DischargeDayPlatelets AS (
    SELECT
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY adm.hadm_id ORDER BY le.charttime DESC) as rn
    FROM SepsisAdmissions sa
    JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm
        ON sa.hadm_id = adm.hadm_id
    JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
        ON adm.subject_id = p.subject_id
    JOIN `physionet-data.mimiciv_3_1_hosp.labevents` le
        ON adm.hadm_id = le.hadm_id
    WHERE
        p.gender = 'M'
        AND le.itemid = 51265
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 10 AND 1000
        AND DATE(le.charttime) = DATE(adm.dischtime)
)
SELECT
    ROUND(APPROX_QUANTILES(valuenum, 100)[OFFSET(75)], 2) AS p75_platelet_count_at_discharge
FROM DischargeDayPlatelets
WHERE rn = 1;
