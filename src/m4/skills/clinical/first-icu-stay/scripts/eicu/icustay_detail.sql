-- ICU stay detail for eICU-CRD: one row per unit stay (patientunitstayid),
-- with the same sequence and first-stay flags as MIMIC-IV's icustay_detail.
--
-- eICU has no dates, so stays are ordered as follows:
--   * Within a hospital stay, earlier unit stays have a higher (less negative)
--     hospitaladmitoffset (MIT-LCP eicu-code, notebooks/patient.ipynb), so unit
--     stays are ordered by hospitaladmitoffset DESC. Tied offsets occur (in
--     eicu-demo, 8 pairs, half of whose rows are zero-length unit stays);
--     unitvisitnumber breaks the tie. patientunitstayid carries no order
--     (https://eicu-crd.mit.edu/eicutables/patient/).
--   * Within a patient, hospitaldischargeyear is the only year available, and
--     the same documentation page states that hospital stays of one patient in
--     the same year cannot be ordered. first_hosp_stay is therefore NULL when
--     the patient has more than one hospital stay in their earliest year.
--
-- Raw patient columns keep their eICU names, as in MIT-LCP eicu-code
-- concepts/icustay_detail.sql (MIT license). Derived columns use the names of
-- MIMIC-IV's icustay_detail (hospital_expire_flag, los_hospital, los_icu), and
-- gender stays as text rather than eicu-code's 0/1 coding.
-- Tested on DuckDB with eicu-demo.

WITH hosp AS (
    -- one row per hospital stay
    SELECT DISTINCT
        uniquepid
        , patienthealthsystemstayid
        , hospitaldischargeyear
    FROM eicu_crd.patient
)

, hosp_seq AS (
    SELECT
        patienthealthsystemstayid
        -- hospital stays discharged in the same year share a sequence number
        , DENSE_RANK() OVER (
            PARTITION BY uniquepid ORDER BY hospitaldischargeyear
        ) AS hospstay_seq
        , COUNT(*) OVER (
            PARTITION BY uniquepid, hospitaldischargeyear
        ) AS hospstays_in_year
    FROM hosp
)

SELECT
    pt.uniquepid
    , pt.patienthealthsystemstayid
    , pt.patientunitstayid

    -- patient level factors
    , pt.gender
    , pt.ethnicity
    , pt.age
    -- age is text; '> 89' is the de-identified top category
    , CASE
        WHEN pt.age = '> 89' THEN 90
        WHEN pt.age IS NULL OR pt.age = '' THEN NULL
        ELSE CAST(pt.age AS INTEGER)
    END AS admission_age

    -- hospital level factors
    , pt.hospitalid
    , pt.hospitaldischargeyear
    , pt.hospitaladmitoffset
    , pt.hospitaldischargeoffset
    , ROUND(
        (pt.hospitaldischargeoffset - pt.hospitaladmitoffset) / 1440.0, 2
    ) AS los_hospital
    , CASE
        WHEN LOWER(pt.hospitaldischargestatus) = 'expired' THEN 1
        WHEN LOWER(pt.hospitaldischargestatus) = 'alive' THEN 0
    END AS hospital_expire_flag
    , hs.hospstay_seq
    , hs.hospstays_in_year
    -- TRUE: only hospital stay in the patient's earliest discharge year
    -- FALSE: a hospital stay with an earlier discharge year exists
    -- NULL: several hospital stays in the earliest year; order unknown
    , CASE
        WHEN hs.hospstay_seq > 1 THEN FALSE
        WHEN hs.hospstays_in_year = 1 THEN TRUE
    END AS first_hosp_stay

    -- icu level factors
    , pt.unittype
    , pt.unitstaytype
    , pt.unitvisitnumber
    , pt.unitdischargeoffset
    , ROUND(pt.unitdischargeoffset / 1440.0, 2) AS los_icu
    , CASE
        WHEN LOWER(pt.unitdischargestatus) = 'expired' THEN 1
        WHEN LOWER(pt.unitdischargestatus) = 'alive' THEN 0
    END AS icu_expire_flag
    , ROW_NUMBER() OVER (
        PARTITION BY pt.patienthealthsystemstayid
        ORDER BY pt.hospitaladmitoffset DESC, pt.unitvisitnumber
    ) AS icustay_seq

    -- first recorded ICU stay *for the current hospitalization*
    , ROW_NUMBER() OVER (
        PARTITION BY pt.patienthealthsystemstayid
        ORDER BY pt.hospitaladmitoffset DESC, pt.unitvisitnumber
    ) = 1 AS first_icu_stay

FROM eicu_crd.patient pt
INNER JOIN hosp_seq hs
    ON pt.patienthealthsystemstayid = hs.patienthealthsystemstayid
