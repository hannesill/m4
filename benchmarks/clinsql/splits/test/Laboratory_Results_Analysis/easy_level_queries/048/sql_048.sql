WITH copd_female_admissions AS (
    SELECT DISTINCT dx.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` dx
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm
        ON dx.hadm_id = adm.hadm_id
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.patients` p
        ON adm.subject_id = p.subject_id
    WHERE
        p.gender = 'F'
        AND (
            dx.icd_code LIKE '491%' OR
            dx.icd_code LIKE '492%' OR
            dx.icd_code = '496' OR
            dx.icd_code LIKE 'J44%'
        )
),
avg_creatinine_first_24h AS (
    SELECT
        le.hadm_id,
        AVG(le.valuenum) AS avg_creatinine_24h
    FROM `physionet-data.mimiciv_3_1_hosp.labevents` le
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` adm
        ON le.hadm_id = adm.hadm_id
    WHERE
        le.itemid = 50912
        AND le.valuenum IS NOT NULL
        AND le.valuenum BETWEEN 0.5 AND 10
        AND le.charttime BETWEEN adm.admittime AND DATETIME_ADD(adm.admittime, INTERVAL 24 HOUR)
    GROUP BY
        le.hadm_id
)
SELECT
    ROUND(APPROX_QUANTILES(creat.avg_creatinine_24h, 100)[OFFSET(75)], 2) AS p75_serum_creatinine
FROM avg_creatinine_first_24h creat
INNER JOIN copd_female_admissions copd
    ON creat.hadm_id = copd.hadm_id;
