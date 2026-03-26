-- SIRS criteria calculated over the first 12 hours of ICU stay
-- (instead of the standard 24-hour window used by mimic-code)
--
-- Uses time-series derived tables (vitalsign, bg, complete_blood_count)
-- with a 12-hour window: intime - 6h to intime + 12h

WITH vitals_12h AS (
    SELECT
        ie.stay_id,
        MIN(v.temperature) AS temperature_min,
        MAX(v.temperature) AS temperature_max,
        MAX(v.heart_rate) AS heart_rate_max,
        MAX(v.resp_rate) AS resp_rate_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.vitalsign v
        ON ie.stay_id = v.stay_id
        AND v.charttime >= ie.intime - INTERVAL '6' HOUR
        AND v.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, bg_art_12h AS (
    SELECT
        ie.stay_id,
        MIN(bg.pco2) AS paco2_min
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.bg bg
        ON ie.subject_id = bg.subject_id
        AND bg.specimen = 'ART.'
        AND bg.charttime >= ie.intime - INTERVAL '6' HOUR
        AND bg.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, labs_12h AS (
    SELECT
        ie.stay_id,
        MIN(cbc.wbc) AS wbc_min,
        MAX(cbc.wbc) AS wbc_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.complete_blood_count cbc
        ON cbc.subject_id = ie.subject_id
        AND cbc.charttime >= ie.intime - INTERVAL '6' HOUR
        AND cbc.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, bands_12h AS (
    SELECT
        ie.stay_id,
        MAX(bd.bands) AS bands_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_derived.blood_differential bd
        ON bd.subject_id = ie.subject_id
        AND bd.charttime >= ie.intime - INTERVAL '6' HOUR
        AND bd.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, scorecomp AS (
    SELECT
        ie.stay_id,
        v.temperature_min,
        v.temperature_max,
        v.heart_rate_max,
        v.resp_rate_max,
        bg.paco2_min,
        l.wbc_min,
        l.wbc_max,
        b.bands_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN vitals_12h v ON ie.stay_id = v.stay_id
    LEFT JOIN bg_art_12h bg ON ie.stay_id = bg.stay_id
    LEFT JOIN labs_12h l ON ie.stay_id = l.stay_id
    LEFT JOIN bands_12h b ON ie.stay_id = b.stay_id
)

, scorecalc AS (
    SELECT stay_id

        , CASE
            WHEN temperature_min < 36.0 THEN 1
            WHEN temperature_max > 38.0 THEN 1
            WHEN temperature_min IS NULL THEN null
            ELSE 0
        END AS temp_score

        , CASE
            WHEN heart_rate_max > 90.0 THEN 1
            WHEN heart_rate_max IS NULL THEN null
            ELSE 0
        END AS heart_rate_score

        , CASE
            WHEN resp_rate_max > 20.0 THEN 1
            WHEN paco2_min < 32.0 THEN 1
            WHEN COALESCE(resp_rate_max, paco2_min) IS NULL THEN null
            ELSE 0
        END AS resp_score

        , CASE
            WHEN wbc_min < 4.0 THEN 1
            WHEN wbc_max > 12.0 THEN 1
            WHEN bands_max > 10 THEN 1
            WHEN COALESCE(wbc_min, bands_max) IS NULL THEN null
            ELSE 0
        END AS wbc_score

    FROM scorecomp
)

SELECT
    ie.subject_id, ie.hadm_id, ie.stay_id
    , COALESCE(temp_score, 0)
    + COALESCE(heart_rate_score, 0)
    + COALESCE(resp_score, 0)
    + COALESCE(wbc_score, 0)
    AS sirs
    , temp_score, heart_rate_score, resp_score, wbc_score
FROM mimiciv_icu.icustays ie
LEFT JOIN scorecalc s
          ON ie.stay_id = s.stay_id
;
