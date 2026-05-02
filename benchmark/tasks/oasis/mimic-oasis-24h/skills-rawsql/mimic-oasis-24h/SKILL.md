# Reference SQL (matched-content control)

The following block is the public reference SQL used to construct the
ground truth for this task. It is provided verbatim, without procedural
prose, to test whether matched task-relevant content alone explains the
WITH-SKILL gain.

```sql
-- ------------------------------------------------------------------
-- Title: Oxford Acute Severity of Illness Score (OASIS)
-- This query extracts the OASIS score for the first 24 hours of each
-- ICU patient's stay. OASIS uses 10 components — vitals, urine output,
-- GCS, ventilation status, age, pre-ICU LOS, and admission type.
-- Notably, it requires NO laboratory values.
-- ------------------------------------------------------------------

-- Reference for OASIS:
--    Johnson AEW, Kramer AA, Clifford GD. "A new severity of illness
--    scale using a subset of APACHE data elements shows comparable
--    predictive accuracy." Crit Care Med. 2013;41(7):1711-1718.

-- Adapted from mimic-code oasis.sql

WITH surgflag AS (
    SELECT
        ie.stay_id,
        MAX(
            CASE
                WHEN LOWER(curr_service) LIKE '%surg%'
                THEN 1
                WHEN curr_service = 'ORTHO'
                THEN 1
                ELSE 0
            END
        ) AS surgical
    FROM mimiciv_icu.icustays AS ie
    LEFT JOIN mimiciv_hosp.services AS se
        ON ie.hadm_id = se.hadm_id AND se.transfertime < ie.intime + INTERVAL '1' DAY
    GROUP BY
        ie.stay_id
)

, vent AS (
    SELECT
        ie.stay_id,
        MAX(CASE WHEN NOT v.stay_id IS NULL THEN 1 ELSE 0 END) AS vent
    FROM mimiciv_icu.icustays AS ie
    LEFT JOIN mimiciv_derived.ventilation AS v
        ON ie.stay_id = v.stay_id
        AND v.ventilation_status = 'InvasiveVent'
        AND (
            (v.starttime >= ie.intime AND v.starttime <= ie.intime + INTERVAL '1' DAY)
            OR (v.endtime >= ie.intime AND v.endtime <= ie.intime + INTERVAL '1' DAY)
            OR (v.starttime <= ie.intime AND v.endtime >= ie.intime + INTERVAL '1' DAY)
        )
    GROUP BY
        ie.stay_id
)

, cohort AS (
    SELECT
        ie.subject_id,
        ie.hadm_id,
        ie.stay_id,
        DATE_DIFF('microseconds', adm.admittime, ie.intime)/60000000.0 AS preiculos,
        ag.age,
        gcs.gcs_min,
        vital.heart_rate_max,
        vital.heart_rate_min,
        vital.mbp_max,
        vital.mbp_min,
        vital.resp_rate_max,
        vital.resp_rate_min,
        vital.temperature_max,
        vital.temperature_min,
        vent.vent AS mechvent,
        uo.urineoutput,
        CASE
            WHEN adm.admission_type = 'ELECTIVE' AND sf.surgical = 1
            THEN 1
            WHEN adm.admission_type IS NULL OR sf.surgical IS NULL
            THEN NULL
            ELSE 0
        END AS electivesurgery
    FROM mimiciv_icu.icustays AS ie
    INNER JOIN mimiciv_hosp.admissions AS adm
        ON ie.hadm_id = adm.hadm_id
    INNER JOIN mimiciv_hosp.patients AS pat
        ON ie.subject_id = pat.subject_id
    LEFT JOIN mimiciv_derived.age AS ag
        ON ie.hadm_id = ag.hadm_id
    LEFT JOIN surgflag AS sf
        ON ie.stay_id = sf.stay_id
    LEFT JOIN mimiciv_derived.first_day_gcs AS gcs
        ON ie.stay_id = gcs.stay_id
    LEFT JOIN mimiciv_derived.first_day_vitalsign AS vital
        ON ie.stay_id = vital.stay_id
    LEFT JOIN mimiciv_derived.first_day_urine_output AS uo
        ON ie.stay_id = uo.stay_id
    LEFT JOIN vent
        ON ie.stay_id = vent.stay_id
)

, scorecomp AS (
    SELECT
        co.subject_id,
        co.hadm_id,
        co.stay_id,
        CASE
            WHEN preiculos IS NULL THEN NULL
            WHEN preiculos < 10.2 THEN 5
            WHEN preiculos < 297 THEN 3
            WHEN preiculos < 1440 THEN 0
            WHEN preiculos < 18708 THEN 2
            ELSE 1
        END AS preiculos_score,
        CASE
            WHEN age IS NULL THEN NULL
            WHEN age < 24 THEN 0
            WHEN age <= 53 THEN 3
            WHEN age <= 77 THEN 6
            WHEN age <= 89 THEN 9
            WHEN age >= 90 THEN 7
            ELSE 0
        END AS age_score,
        CASE
            WHEN gcs_min IS NULL THEN NULL
            WHEN gcs_min <= 7 THEN 10
            WHEN gcs_min < 14 THEN 4
            WHEN gcs_min = 14 THEN 3
            ELSE 0
        END AS gcs_score,
        CASE
            WHEN heart_rate_max IS NULL THEN NULL
            WHEN heart_rate_max > 125 THEN 6
            WHEN heart_rate_min < 33 THEN 4
            WHEN heart_rate_max >= 107 AND heart_rate_max <= 125 THEN 3
            WHEN heart_rate_max >= 89 AND heart_rate_max <= 106 THEN 1
            ELSE 0
        END AS heart_rate_score,
        CASE
            WHEN mbp_min IS NULL THEN NULL
            WHEN mbp_min < 20.65 THEN 4
            WHEN mbp_min < 51 THEN 3
            WHEN mbp_max > 143.44 THEN 3
            WHEN mbp_min >= 51 AND mbp_min < 61.33 THEN 2
            ELSE 0
        END AS mbp_score,
        CASE
            WHEN resp_rate_min IS NULL THEN NULL
            WHEN resp_rate_min < 6 THEN 10
            WHEN resp_rate_max > 44 THEN 9
            WHEN resp_rate_max > 30 THEN 6
            WHEN resp_rate_max > 22 THEN 1
            WHEN resp_rate_min < 13 THEN 1
            ELSE 0
        END AS resp_rate_score,
        CASE
            WHEN temperature_max IS NULL THEN NULL
            WHEN temperature_max > 39.88 THEN 6
            WHEN temperature_min >= 33.22 AND temperature_min <= 35.93 THEN 4
            WHEN temperature_max >= 33.22 AND temperature_max <= 35.93 THEN 4
            WHEN temperature_min < 33.22 THEN 3
            WHEN temperature_min > 35.93 AND temperature_min <= 36.39 THEN 2
            WHEN temperature_max >= 36.89 AND temperature_max <= 39.88 THEN 2
            ELSE 0
        END AS temp_score,
        CASE
            WHEN urineoutput IS NULL THEN NULL
            WHEN urineoutput < 671.09 THEN 10
            WHEN urineoutput > 6896.80 THEN 8
            WHEN urineoutput >= 671.09 AND urineoutput <= 1426.99 THEN 5
            WHEN urineoutput >= 1427.00 AND urineoutput <= 2544.14 THEN 1
            ELSE 0
        END AS urineoutput_score,
        CASE
            WHEN mechvent IS NULL THEN NULL
            WHEN mechvent = 1 THEN 9
            ELSE 0
        END AS mechvent_score,
        CASE
            WHEN electivesurgery IS NULL THEN NULL
            WHEN electivesurgery = 1 THEN 0
            ELSE 6
        END AS electivesurgery_score
    FROM cohort AS co
)

SELECT
    subject_id, hadm_id, stay_id
    -- Combine all scores to get OASIS total
    -- Impute 0 if the score is missing
    , COALESCE(preiculos_score, 0)
    + COALESCE(age_score, 0)
    + COALESCE(gcs_score, 0)
    + COALESCE(heart_rate_score, 0)
    + COALESCE(mbp_score, 0)
    + COALESCE(resp_rate_score, 0)
    + COALESCE(temp_score, 0)
    + COALESCE(urineoutput_score, 0)
    + COALESCE(mechvent_score, 0)
    + COALESCE(electivesurgery_score, 0)
    AS oasis
    -- DEVIATION from mimic-code: COALESCE component scores to 0.
    -- See sofa-24h.sql for rationale.
    , COALESCE(preiculos_score, 0) AS preiculos_score
    , COALESCE(age_score, 0) AS age_score
    , COALESCE(gcs_score, 0) AS gcs_score
    , COALESCE(heart_rate_score, 0) AS heart_rate_score
    , COALESCE(mbp_score, 0) AS mbp_score
    , COALESCE(resp_rate_score, 0) AS resp_rate_score
    , COALESCE(temp_score, 0) AS temp_score
    , COALESCE(urineoutput_score, 0) AS urineoutput_score
    , COALESCE(mechvent_score, 0) AS mechvent_score
    , COALESCE(electivesurgery_score, 0) AS electivesurgery_score
FROM scorecomp
;
```
