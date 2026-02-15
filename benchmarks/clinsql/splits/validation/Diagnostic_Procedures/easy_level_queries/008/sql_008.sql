SELECT
    APPROX_QUANTILES(echo_count, 100)[OFFSET(25)] AS p25_echo_count
FROM (
    SELECT
        p.subject_id,
        COUNT(DISTINCT pr.icd_code) AS echo_count
    FROM
        `physionet-data.mimiciv_3_1_hosp.patients` p
    JOIN
        `physionet-data.mimiciv_3_1_hosp.procedures_icd` pr ON p.subject_id = pr.subject_id
    WHERE
        p.gender = 'F'
        AND p.anchor_age BETWEEN 88 AND 98
        AND (
            (pr.icd_version = 9 AND pr.icd_code = '88.72')
            OR
            (pr.icd_version = 10 AND pr.icd_code LIKE 'B24%')
        )
    GROUP BY
        p.subject_id
) AS patient_echo_counts;
