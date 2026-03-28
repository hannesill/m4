-- SOFA score calculated over the first 12 hours of ICU stay
-- (instead of the standard 24-hour window used by mimic-code)
--
-- Uses time-series derived tables (vitalsign, bg, chemistry, enzyme,
-- complete_blood_count, gcs, vasopressors) with a 12-hour window:
-- intime - 6h to intime + 12h
--
-- NOTE: Urine output criteria are NOT applied for the renal component.
-- The SOFA renal UO thresholds are defined in mL/day (< 500, < 200),
-- which requires 24 hours of data. Using partial UO from a 12h window
-- would be methodologically incorrect. Only serum creatinine is used
-- for renal scoring in this variant.

WITH pafi1 AS (
    SELECT
        ie.stay_id,
        bg.charttime,
        bg.pao2fio2ratio,
        CASE WHEN NOT vd.stay_id IS NULL THEN 1 ELSE 0 END AS isvent
    FROM mimiciv_icu.icustays AS ie
    -- [REVIEW] mimic-code omits specimen='ART.' here, unlike the hourly
    -- sofa.sql which filters arterial only. This means venous PaO2/FiO2
    -- values may contribute to the respiration score. Consider adding:
    --     AND bg.specimen = 'ART.'
    LEFT JOIN mimiciv_derived.bg AS bg
        ON ie.subject_id = bg.subject_id
        AND bg.charttime >= ie.intime - INTERVAL '6' HOUR
        AND bg.charttime <= ie.intime + INTERVAL '12' HOUR
    LEFT JOIN mimiciv_derived.ventilation AS vd
        ON ie.stay_id = vd.stay_id
        AND bg.charttime >= vd.starttime
        AND bg.charttime <= vd.endtime
        AND vd.ventilation_status = 'InvasiveVent'
)

, pafi2 AS (
    SELECT
        stay_id,
        MIN(CASE WHEN isvent = 0 THEN pao2fio2ratio ELSE NULL END) AS pao2fio2_novent_min,
        MIN(CASE WHEN isvent = 1 THEN pao2fio2ratio ELSE NULL END) AS pao2fio2_vent_min
    FROM pafi1
    GROUP BY
        stay_id
)

, vitals_12h AS (
    SELECT
        ie.stay_id,
        MIN(v.mbp) AS mbp_min
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.vitalsign v
        ON ie.stay_id = v.stay_id
        AND v.charttime >= ie.intime - INTERVAL '6' HOUR
        AND v.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, labs_12h AS (
    SELECT
        ie.stay_id,
        MAX(chem.creatinine) AS creatinine_max,
        MAX(enz.bilirubin_total) AS bilirubin_max,
        MIN(cbc.platelet) AS platelet_min
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.chemistry chem
        ON ie.hadm_id = chem.hadm_id
        AND chem.charttime >= ie.intime - INTERVAL '6' HOUR
        AND chem.charttime <= ie.intime + INTERVAL '12' HOUR
    LEFT JOIN mimiciv_derived.enzyme enz
        ON ie.hadm_id = enz.hadm_id
        AND enz.charttime >= ie.intime - INTERVAL '6' HOUR
        AND enz.charttime <= ie.intime + INTERVAL '12' HOUR
    LEFT JOIN mimiciv_derived.complete_blood_count cbc
        ON ie.hadm_id = cbc.hadm_id
        AND cbc.charttime >= ie.intime - INTERVAL '6' HOUR
        AND cbc.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, gcs_12h AS (
    SELECT
        ie.stay_id,
        MIN(gcs.gcs) AS gcs_min
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.gcs gcs
        ON ie.stay_id = gcs.stay_id
        AND gcs.charttime >= ie.intime - INTERVAL '6' HOUR
        AND gcs.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, vaso_stg AS (
    SELECT
        ie.stay_id,
        'norepinephrine' AS treatment,
        vaso_rate AS rate
    FROM mimiciv_icu.icustays AS ie
    INNER JOIN mimiciv_derived.norepinephrine AS mv
        ON ie.stay_id = mv.stay_id
        AND mv.starttime >= ie.intime - INTERVAL '6' HOUR
        AND mv.starttime <= ie.intime + INTERVAL '12' HOUR
    UNION ALL
    SELECT
        ie.stay_id,
        'epinephrine' AS treatment,
        vaso_rate AS rate
    FROM mimiciv_icu.icustays AS ie
    INNER JOIN mimiciv_derived.epinephrine AS mv
        ON ie.stay_id = mv.stay_id
        AND mv.starttime >= ie.intime - INTERVAL '6' HOUR
        AND mv.starttime <= ie.intime + INTERVAL '12' HOUR
    UNION ALL
    SELECT
        ie.stay_id,
        'dobutamine' AS treatment,
        vaso_rate AS rate
    FROM mimiciv_icu.icustays AS ie
    INNER JOIN mimiciv_derived.dobutamine AS mv
        ON ie.stay_id = mv.stay_id
        AND mv.starttime >= ie.intime - INTERVAL '6' HOUR
        AND mv.starttime <= ie.intime + INTERVAL '12' HOUR
    UNION ALL
    SELECT
        ie.stay_id,
        'dopamine' AS treatment,
        vaso_rate AS rate
    FROM mimiciv_icu.icustays AS ie
    INNER JOIN mimiciv_derived.dopamine AS mv
        ON ie.stay_id = mv.stay_id
        AND mv.starttime >= ie.intime - INTERVAL '6' HOUR
        AND mv.starttime <= ie.intime + INTERVAL '12' HOUR
)

, vaso_12h AS (
    SELECT
        ie.stay_id,
        MAX(CASE WHEN treatment = 'norepinephrine' THEN rate ELSE NULL END) AS rate_norepinephrine,
        MAX(CASE WHEN treatment = 'epinephrine' THEN rate ELSE NULL END) AS rate_epinephrine,
        MAX(CASE WHEN treatment = 'dopamine' THEN rate ELSE NULL END) AS rate_dopamine,
        MAX(CASE WHEN treatment = 'dobutamine' THEN rate ELSE NULL END) AS rate_dobutamine
    FROM mimiciv_icu.icustays AS ie
    LEFT JOIN vaso_stg AS v
        ON ie.stay_id = v.stay_id
    GROUP BY
        ie.stay_id
)

, scorecomp AS (
    SELECT
        ie.stay_id,
        v.mbp_min,
        mv.rate_norepinephrine,
        mv.rate_epinephrine,
        mv.rate_dopamine,
        mv.rate_dobutamine,
        l.creatinine_max,
        l.bilirubin_max,
        l.platelet_min,
        pf.pao2fio2_novent_min,
        pf.pao2fio2_vent_min,
        gcs.gcs_min
    FROM mimiciv_icu.icustays AS ie
    LEFT JOIN vaso_12h AS mv
        ON ie.stay_id = mv.stay_id
    LEFT JOIN pafi2 AS pf
        ON ie.stay_id = pf.stay_id
    LEFT JOIN vitals_12h AS v
        ON ie.stay_id = v.stay_id
    LEFT JOIN labs_12h AS l
        ON ie.stay_id = l.stay_id
    LEFT JOIN gcs_12h AS gcs
        ON ie.stay_id = gcs.stay_id
)

, scorecalc AS (
    SELECT
        stay_id,
        CASE
            WHEN pao2fio2_vent_min < 100
            THEN 4
            WHEN pao2fio2_vent_min < 200
            THEN 3
            WHEN pao2fio2_novent_min < 300
            THEN 2
            WHEN pao2fio2_novent_min < 400
            THEN 1
            WHEN COALESCE(pao2fio2_vent_min, pao2fio2_novent_min) IS NULL
            THEN NULL
            ELSE 0
        END AS respiration,
        CASE
            WHEN platelet_min < 20
            THEN 4
            WHEN platelet_min < 50
            THEN 3
            WHEN platelet_min < 100
            THEN 2
            WHEN platelet_min < 150
            THEN 1
            WHEN platelet_min IS NULL
            THEN NULL
            ELSE 0
        END AS coagulation,
        CASE
            WHEN bilirubin_max >= 12.0
            THEN 4
            WHEN bilirubin_max >= 6.0
            THEN 3
            WHEN bilirubin_max >= 2.0
            THEN 2
            WHEN bilirubin_max >= 1.2
            THEN 1
            WHEN bilirubin_max IS NULL
            THEN NULL
            ELSE 0
        END AS liver,
        CASE
            WHEN rate_dopamine > 15 OR rate_epinephrine > 0.1 OR rate_norepinephrine > 0.1
            THEN 4
            -- BUG (inherited from mimic-code): <= 0.1 is TRUE for any
            -- non-NULL rate, making scores 2/1/0 unreachable when epi or
            -- norepi is present. Correct intent is > 0 (i.e. drug is being
            -- administered at any dose up to 0.1). Kept as-is to match
            -- mimic-code; harmless in practice because the derived
            -- vasopressor tables only contain rows with positive rates.
            WHEN rate_dopamine > 5 OR rate_epinephrine <= 0.1 OR rate_norepinephrine <= 0.1
            THEN 3
            WHEN rate_dopamine > 0 OR rate_dobutamine > 0
            THEN 2
            WHEN mbp_min < 70
            THEN 1
            WHEN COALESCE(mbp_min, rate_dopamine, rate_dobutamine, rate_epinephrine, rate_norepinephrine) IS NULL
            THEN NULL
            ELSE 0
        END AS cardiovascular,
        CASE
            WHEN (gcs_min >= 13 AND gcs_min <= 14)
            THEN 1
            WHEN (gcs_min >= 10 AND gcs_min <= 12)
            THEN 2
            WHEN (gcs_min >= 6 AND gcs_min <= 9)
            THEN 3
            WHEN gcs_min < 6
            THEN 4
            WHEN gcs_min IS NULL
            THEN NULL
            ELSE 0
        END AS cns,
        -- Renal: creatinine only (no urine output for 12h window)
        CASE
            WHEN (creatinine_max >= 5.0)
            THEN 4
            WHEN (creatinine_max >= 3.5 AND creatinine_max < 5.0)
            THEN 3
            WHEN (creatinine_max >= 2.0 AND creatinine_max < 3.5)
            THEN 2
            WHEN (creatinine_max >= 1.2 AND creatinine_max < 2.0)
            THEN 1
            WHEN creatinine_max IS NULL
            THEN NULL
            ELSE 0
        END AS renal
    FROM scorecomp
)

SELECT
    ie.subject_id, ie.hadm_id, ie.stay_id
    -- Combine all the scores to get SOFA
    -- Impute 0 if the score is missing
    , COALESCE(respiration, 0)
    + COALESCE(coagulation, 0)
    + COALESCE(liver, 0)
    + COALESCE(cardiovascular, 0)
    + COALESCE(cns, 0)
    + COALESCE(renal, 0)
    AS sofa
    -- DEVIATION from mimic-code: COALESCE component scores to 0.
    -- See sofa-24h.sql for rationale.
    , COALESCE(respiration, 0) AS respiration
    , COALESCE(coagulation, 0) AS coagulation
    , COALESCE(liver, 0) AS liver
    , COALESCE(cardiovascular, 0) AS cardiovascular
    , COALESCE(cns, 0) AS cns
    , COALESCE(renal, 0) AS renal
FROM mimiciv_icu.icustays ie
LEFT JOIN scorecalc s
          ON ie.stay_id = s.stay_id
;
