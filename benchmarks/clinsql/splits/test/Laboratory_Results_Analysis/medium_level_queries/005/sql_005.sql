WITH chest_pain_ami_admissions AS (
    SELECT DISTINCT
        hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.diagnoses_icd`
    WHERE
        (icd_version = 9 AND SUBSTR(icd_code, 1, 3) = '410') OR
        (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'I21') OR
        (icd_version = 9 AND SUBSTR(icd_code, 1, 4) = '7865') OR
        (icd_version = 10 AND SUBSTR(icd_code, 1, 3) = 'R07')
),
target_population AS (
    SELECT
        p.subject_id,
        a.hadm_id
    FROM `physionet-data.mimiciv_3_1_hosp.patients` AS p
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.admissions` AS a
        ON p.subject_id = a.subject_id
    INNER JOIN chest_pain_ami_admissions AS cpaa
        ON a.hadm_id = cpaa.hadm_id
    WHERE
        p.gender = 'M'
        AND (p.anchor_age + EXTRACT(YEAR FROM a.admittime) - p.anchor_year) BETWEEN 35 AND 45
        AND a.admittime IS NOT NULL
),
initial_troponin AS (
    SELECT
        tp.subject_id,
        tp.hadm_id,
        le.valuenum,
        ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as measurement_rank
    FROM target_population AS tp
    INNER JOIN `physionet-data.mimiciv_3_1_hosp.labevents` AS le
        ON tp.hadm_id = le.hadm_id
    WHERE
        le.itemid = 51003
        AND le.valuenum IS NOT NULL
        AND le.valuenum >= 0
)
SELECT
    CASE
        WHEN valuenum < 0.014 THEN 'Normal (< 0.014 ng/mL)'
        WHEN valuenum >= 0.014 AND valuenum <= 0.052 THEN 'Borderline (0.014-0.052 ng/mL)'
        WHEN valuenum > 0.052 THEN 'Myocardial Injury (> 0.052 ng/mL)'
        ELSE 'Unknown'
    END AS troponin_category,
    COUNT(DISTINCT subject_id) AS patient_count
FROM initial_troponin
WHERE
    measurement_rank = 1
GROUP BY
    troponin_category
ORDER BY
    CASE
        WHEN troponin_category LIKE 'Normal%' THEN 1
        WHEN troponin_category LIKE 'Borderline%' THEN 2
        WHEN troponin_category LIKE 'Myocardial Injury%' THEN 3
        ELSE 4
    END;
