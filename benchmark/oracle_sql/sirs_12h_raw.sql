-- SIRS criteria calculated from RAW tables only (no mimiciv_derived)
-- 12-hour window: intime - 6h to intime + 12h

WITH vitals_raw AS (
    SELECT
        ie.stay_id,
        MIN(CASE
            WHEN ce.itemid = 223762 AND ce.valuenum > 10 AND ce.valuenum < 50
                THEN ce.valuenum  -- Celsius
            WHEN ce.itemid = 223761 AND ce.valuenum > 70 AND ce.valuenum < 120
                THEN (ce.valuenum - 32) / 1.8  -- Fahrenheit → Celsius
        END) AS temperature_min,
        MAX(CASE
            WHEN ce.itemid = 223762 AND ce.valuenum > 10 AND ce.valuenum < 50
                THEN ce.valuenum
            WHEN ce.itemid = 223761 AND ce.valuenum > 70 AND ce.valuenum < 120
                THEN (ce.valuenum - 32) / 1.8
        END) AS temperature_max,
        MAX(CASE
            WHEN ce.itemid = 220045 AND ce.valuenum > 0 AND ce.valuenum < 300
                THEN ce.valuenum
        END) AS heart_rate_max,
        MAX(CASE
            WHEN ce.itemid IN (220210, 224690) AND ce.valuenum > 0 AND ce.valuenum < 70
                THEN ce.valuenum
        END) AS resp_rate_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_icu.chartevents ce
        ON ie.stay_id = ce.stay_id
        AND ce.itemid IN (223761, 223762, 220045, 220210, 224690)
        AND ce.charttime >= ie.intime - INTERVAL '6' HOUR
        AND ce.charttime <= ie.intime + INTERVAL '12' HOUR
    GROUP BY ie.stay_id
)

, bg_raw AS (
    SELECT
        ie.stay_id,
        MIN(CASE WHEN le.itemid = 50818 THEN le.valuenum END) AS paco2_min
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_hosp.labevents le
        ON le.subject_id = ie.subject_id
        AND le.itemid IN (50818, 52033)
        AND le.charttime >= ie.intime - INTERVAL '6' HOUR
        AND le.charttime <= ie.intime + INTERVAL '12' HOUR
    WHERE le.specimen_id IS NULL
       OR le.specimen_id IN (
            SELECT specimen_id FROM mimiciv_hosp.labevents
            WHERE itemid = 52033 AND value = 'ART.'
        )
    GROUP BY ie.stay_id
)

, labs_raw AS (
    SELECT
        ie.stay_id,
        MIN(CASE WHEN le.itemid IN (51300, 51301) THEN le.valuenum END) AS wbc_min,
        MAX(CASE WHEN le.itemid IN (51300, 51301) THEN le.valuenum END) AS wbc_max,
        MAX(CASE WHEN le.itemid = 51144 THEN le.valuenum END) AS bands_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN mimiciv_hosp.labevents le
        ON le.subject_id = ie.subject_id
        AND le.itemid IN (51300, 51301, 51144)
        AND le.charttime >= ie.intime - INTERVAL '6' HOUR
        AND le.charttime <= ie.intime + INTERVAL '12' HOUR
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
        l.bands_max
    FROM mimiciv_icu.icustays ie
    LEFT JOIN vitals_raw v ON ie.stay_id = v.stay_id
    LEFT JOIN bg_raw bg ON ie.stay_id = bg.stay_id
    LEFT JOIN labs_raw l ON ie.stay_id = l.stay_id
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
