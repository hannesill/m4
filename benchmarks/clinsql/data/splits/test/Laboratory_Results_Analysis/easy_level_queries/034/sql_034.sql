WITH HeartFailureAdmissions AS (
SELECT DISTINCT
    diag.hadm_id
FROM
    `physionet-data.mimiciv_3_1_hosp.patients` p
JOIN
    `physionet-data.mimiciv_3_1_hosp.diagnoses_icd` diag ON p.subject_id = diag.subject_id
WHERE
    p.gender = 'M'
    AND (
        STARTS_WITH(diag.icd_code, '428')
        OR STARTS_WITH(diag.icd_code, 'I50')
    )
),
AdmissionSodium AS (
SELECT
    le.valuenum,
    ROW_NUMBER() OVER(PARTITION BY le.hadm_id ORDER BY le.charttime ASC) as rn
FROM
    `physionet-data.mimiciv_3_1_hosp.labevents` le
JOIN
    HeartFailureAdmissions hfa ON le.hadm_id = hfa.hadm_id
WHERE
    le.itemid = 50983
    AND le.valuenum IS NOT NULL
    AND le.valuenum BETWEEN 120 AND 160
)
SELECT
    MIN(valuenum) AS min_admission_serum_sodium
FROM
    AdmissionSodium
WHERE
    rn = 1;
