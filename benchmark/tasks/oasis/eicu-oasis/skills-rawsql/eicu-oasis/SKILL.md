# Reference SQL (matched-content control)

The following block is the public reference SQL used to construct the
ground truth for this task. It is provided verbatim, without procedural
prose, to test whether matched task-relevant content alone explains the
WITH-SKILL gain.

```sql
-- ------------------------------------------------------------------
-- Title: Oxford Acute Severity of Illness Score (OASIS) — eICU
-- Matches eicu-code pivoted-oasis.sql logic exactly, inlining the
-- derived tables (pivoted_vital, pivoted_gcs, pivoted_uo).
-- ------------------------------------------------------------------

-- Reference:
--    Johnson AEW, Kramer AA, Clifford GD. "A new severity of illness
--    scale using a subset of APACHE data elements shows comparable
--    predictive accuracy." Crit Care Med. 2013;41(7):1711-1718.

-- Adapted from eicu-code pivoted-oasis.sql (BigQuery → DuckDB)
-- Inlines: pivoted-vital.sql, pivoted-gcs.sql, pivoted-uo.sql

-- ══════════════════════════════════════════════════════════════════
-- Pre-ICU LOS
-- ══════════════════════════════════════════════════════════════════
WITH pre_icu_los_data AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN hospitaladmitoffset > (-0.17 * 60) THEN 5
            WHEN hospitaladmitoffset BETWEEN (-4.94 * 60) AND (-0.17 * 60) THEN 3
            WHEN hospitaladmitoffset BETWEEN (-24 * 60) AND (-4.94 * 60) THEN 0
            WHEN hospitaladmitoffset BETWEEN (-311.80 * 60) AND (-24.0 * 60) THEN 2
            WHEN hospitaladmitoffset < (-311.80 * 60) THEN 1
            ELSE NULL
        END AS pre_icu_los_oasis
    FROM eicu_crd.patient
)

-- ══════════════════════════════════════════════════════════════════
-- Age
-- ══════════════════════════════════════════════════════════════════
, age_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN MAX(CASE WHEN age = '> 89' THEN 91 ELSE TRY_CAST(age AS INT) END) < 24 THEN 0
            WHEN MAX(CASE WHEN age = '> 89' THEN 91 ELSE TRY_CAST(age AS INT) END) BETWEEN 24 AND 53 THEN 3
            WHEN MAX(CASE WHEN age = '> 89' THEN 91 ELSE TRY_CAST(age AS INT) END) BETWEEN 54 AND 77 THEN 6
            WHEN MAX(CASE WHEN age = '> 89' THEN 91 ELSE TRY_CAST(age AS INT) END) BETWEEN 78 AND 89 THEN 9
            WHEN MAX(CASE WHEN age = '> 89' THEN 91 ELSE TRY_CAST(age AS INT) END) > 89 THEN 7
            ELSE NULL
        END AS age_oasis
    FROM eicu_crd.patient
    GROUP BY patientunitstayid
)

-- ══════════════════════════════════════════════════════════════════
-- GCS — inlined from pivoted-gcs.sql + physicalexam
-- ══════════════════════════════════════════════════════════════════

-- GCS from nursecharting (pivoted-gcs logic)
, nc_gcs AS (
    SELECT
        patientunitstayid,
        nursingchartoffset AS chartoffset,
        MIN(CASE
            WHEN nursingchartcelltypevallabel = 'Glasgow coma score'
             AND nursingchartcelltypevalname = 'GCS Total'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            WHEN nursingchartcelltypevallabel = 'Score (Glasgow Coma Scale)'
             AND nursingchartcelltypevalname = 'Value'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END) AS gcs
    FROM eicu_crd.nursecharting
    WHERE nursingchartcelltypecat IN ('Scores', 'Other Vital Signs and Infusions')
    GROUP BY patientunitstayid, nursingchartoffset
)

, pivoted_gcs AS (
    SELECT
        patientunitstayid,
        chartoffset,
        CASE WHEN gcs > 2 AND gcs < 16 THEN gcs ELSE NULL END AS gcs
    FROM nc_gcs
    WHERE gcs IS NOT NULL
)

-- GCS from physicalexam (secondary source, matches eicu-code)
, physexam_gcs AS (
    SELECT
        patientunitstayid,
        MIN(TRY_CAST(physicalexamvalue AS NUMERIC)) AS gcs
    FROM eicu_crd.physicalexam
    WHERE (
        physicalexampath LIKE 'notes/Progress Notes/Physical Exam/Physical Exam/Neurologic/GCS/_'
        OR physicalexampath LIKE 'notes/Progress Notes/Physical Exam/Physical Exam/Neurologic/GCS/__'
    )
    AND physicalexamoffset > 0
    AND physicalexamoffset <= 1440
    AND physicalexamvalue IS NOT NULL
    GROUP BY patientunitstayid
)

-- Merge GCS sources: prefer nursecharting, fallback to physicalexam
, merged_gcs AS (
    SELECT
        p.patientunitstayid,
        COALESCE(
            (SELECT MIN(pg.gcs) FROM pivoted_gcs pg
             WHERE pg.patientunitstayid = p.patientunitstayid
             AND pg.chartoffset > 0 AND pg.chartoffset <= 1440),
            pe.gcs
        ) AS gcs_min
    FROM eicu_crd.patient p
    LEFT JOIN physexam_gcs pe ON p.patientunitstayid = pe.patientunitstayid
)

, gcs_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN gcs_min < 8 THEN 10
            WHEN gcs_min BETWEEN 8 AND 13 THEN 4
            WHEN gcs_min = 14 THEN 3
            WHEN gcs_min = 15 THEN 0
            ELSE NULL
        END AS gcs_oasis
    FROM merged_gcs
)

-- ══════════════════════════════════════════════════════════════════
-- Vitals — inlined from pivoted-vital.sql (nursecharting-based)
-- ══════════════════════════════════════════════════════════════════
, nc_vitals AS (
    SELECT
        patientunitstayid,
        nursingchartoffset AS chartoffset,
        -- Heart rate
        CASE
            WHEN nursingchartcelltypevallabel = 'Heart Rate'
             AND nursingchartcelltypevalname = 'Heart Rate'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END AS heartrate,
        -- Respiratory rate
        CASE
            WHEN nursingchartcelltypevallabel = 'Respiratory Rate'
             AND nursingchartcelltypevalname = 'Respiratory Rate'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END AS respiratoryrate,
        -- Temperature (Celsius)
        CASE
            WHEN nursingchartcelltypevallabel = 'Temperature'
             AND nursingchartcelltypevalname = 'Temperature (C)'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END AS temperature,
        -- Invasive BP Mean
        CASE
            WHEN nursingchartcelltypevallabel = 'Invasive BP'
             AND nursingchartcelltypevalname = 'Invasive BP Mean'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            WHEN nursingchartcelltypevallabel = 'MAP (mmHg)'
             AND nursingchartcelltypevalname = 'Value'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            WHEN nursingchartcelltypevallabel = 'Arterial Line MAP (mmHg)'
             AND nursingchartcelltypevalname = 'Value'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END AS ibp_mean,
        -- Non-invasive BP Mean
        CASE
            WHEN nursingchartcelltypevallabel = 'Non-Invasive BP'
             AND nursingchartcelltypevalname = 'Non-Invasive BP Mean'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END AS nibp_mean
    FROM eicu_crd.nursecharting
    WHERE nursingchartcelltypecat IN ('Vital Signs', 'Scores', 'Other Vital Signs and Infusions')
)

-- Apply range validation (matching pivoted-vital.sql) and aggregate
, pivoted_vital_agg AS (
    SELECT
        patientunitstayid,
        -- Heart rate (valid: 25-225)
        MIN(CASE WHEN heartrate >= 25 AND heartrate <= 225 THEN heartrate END) AS hr_min,
        MAX(CASE WHEN heartrate >= 25 AND heartrate <= 225 THEN heartrate END) AS hr_max,
        -- Respiratory rate (valid: 0-60, but exclude 0 for min)
        MIN(CASE WHEN respiratoryrate > 0 AND respiratoryrate <= 60 THEN respiratoryrate END) AS rr_min,
        MAX(CASE WHEN respiratoryrate >= 0 AND respiratoryrate <= 60 THEN respiratoryrate END) AS rr_max,
        -- Temperature (valid: 25-46)
        MIN(CASE WHEN temperature >= 25 AND temperature <= 46 THEN temperature END) AS temp_min,
        MAX(CASE WHEN temperature >= 25 AND temperature <= 46 THEN temperature END) AS temp_max,
        -- Invasive BP mean (valid: 1-250)
        MIN(CASE WHEN ibp_mean >= 1 AND ibp_mean <= 250 THEN ibp_mean END) AS ibp_mean_min,
        MAX(CASE WHEN ibp_mean >= 1 AND ibp_mean <= 250 THEN ibp_mean END) AS ibp_mean_max,
        -- Non-invasive BP mean (valid: 1-250)
        MIN(CASE WHEN nibp_mean >= 1 AND nibp_mean <= 250 THEN nibp_mean END) AS nibp_mean_min,
        MAX(CASE WHEN nibp_mean >= 1 AND nibp_mean <= 250 THEN nibp_mean END) AS nibp_mean_max
    FROM nc_vitals
    WHERE chartoffset > 0 AND chartoffset <= 1440
    GROUP BY patientunitstayid
)

-- Heart rate score
, heartrate_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN hr_min < 33 THEN 4
            WHEN hr_max BETWEEN 33 AND 88 THEN 0
            WHEN hr_max BETWEEN 89 AND 106 THEN 1
            WHEN hr_max BETWEEN 107 AND 125 THEN 3
            WHEN hr_max > 125 THEN 6
            ELSE NULL
        END AS heartrate_oasis
    FROM pivoted_vital_agg
    WHERE hr_min IS NOT NULL OR hr_max IS NOT NULL
)

-- MAP score — tries ibp_mean first, then nibp_mean (matching eicu-code)
, map_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN ibp_mean_min < 20.65 THEN 4
            WHEN ibp_mean_min BETWEEN 20.65 AND 50.99 THEN 3
            WHEN ibp_mean_min BETWEEN 51 AND 61.32 THEN 2
            WHEN ibp_mean_min BETWEEN 61.33 AND 143.44 THEN 0
            WHEN ibp_mean_max > 143.44 THEN 3

            WHEN nibp_mean_min < 20.65 THEN 4
            WHEN nibp_mean_min BETWEEN 20.65 AND 50.99 THEN 3
            WHEN nibp_mean_min BETWEEN 51 AND 61.32 THEN 2
            WHEN nibp_mean_min BETWEEN 61.33 AND 143.44 THEN 0
            WHEN nibp_mean_max > 143.44 THEN 3
            ELSE NULL
        END AS map_oasis
    FROM pivoted_vital_agg
)

-- Respiratory rate score
, respiratoryrate_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN rr_min < 6 THEN 10
            WHEN rr_min BETWEEN 6 AND 12 THEN 1
            WHEN rr_min BETWEEN 13 AND 22 THEN 0
            WHEN rr_max BETWEEN 23 AND 30 THEN 1
            WHEN rr_max BETWEEN 31 AND 44 THEN 6
            WHEN rr_max > 44 THEN 9
            ELSE NULL
        END AS respiratoryrate_oasis
    FROM pivoted_vital_agg
    WHERE rr_min IS NOT NULL OR rr_max IS NOT NULL
)

-- Temperature score
, temperature_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN temp_min < 33.22 THEN 3
            WHEN temp_min BETWEEN 33.22 AND 35.93 THEN 4
            WHEN temp_max BETWEEN 33.22 AND 35.93 THEN 4
            WHEN temp_min BETWEEN 35.94 AND 36.39 THEN 2
            WHEN temp_max BETWEEN 36.40 AND 36.88 THEN 0
            WHEN temp_max BETWEEN 36.89 AND 39.88 THEN 2
            WHEN temp_max > 39.88 THEN 6
            ELSE NULL
        END AS temperature_oasis
    FROM pivoted_vital_agg
    WHERE temp_min IS NOT NULL OR temp_max IS NOT NULL
)

-- ══════════════════════════════════════════════════════════════════
-- Urine Output — inlined from pivoted-uo.sql (exact cellpath list)
-- ══════════════════════════════════════════════════════════════════
, uo_raw AS (
    SELECT
        patientunitstayid,
        intakeoutputoffset,
        cellvaluenumeric,
        CASE
            WHEN cellpath NOT LIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|%' THEN 0
            WHEN cellpath IN (
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|3 way foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|3 Way Foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Actual Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Adjusted total UO NOC end shift',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|BRP (urine)',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|BRP (Urine)',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|condome cath urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|diaper urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|inc of urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incontient urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incontient urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incontient Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incontinence of urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incontinence-urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incontinence/ voids urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incontinent of urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|INCONTINENT OF URINE',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incontinent UOP',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incontinent urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incontinent (urine)',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incontinent Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incontinent urine counts',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incont of urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incont. of urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incont. of urine count',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incont urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|incont. urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incont. urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Incont. Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|inc urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|inc. urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Inc. urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Inc Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|indwelling foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Indwelling Foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Catheter-Foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Catheterization Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Cath UOP',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|straight cath urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Cath Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|strait cath Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Suprapubic Urine Output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|true urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|True Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|True Urine out',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|unmeasured urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Unmeasured Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|unmeasured urine output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urethal Catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urethral Catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|urinary output 7AM - 7 PM',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|urinary output 7AM-7PM',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|URINE',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|URINE CATHETER',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Intermittent/Straight Cath (mL)',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|straightcath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|straight cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight  cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight  Cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Cath''d',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|straight cath daily',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|straight cathed',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Cathed',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight catheterization',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Catheter Output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Catheter-Straight Catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|straight cath ml''s',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight cath ml''s',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight Cath Q6hrs',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Straight caths',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-straight cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine-straight cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Straight Cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Condom Catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|condom catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|condom cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Condom Cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|CONDOM CATHETER OUTPUT',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine via condom catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine-foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine- foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine- Foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine foley catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine, L neph:',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine (measured)',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|urine output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-external catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Foley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-FOLEY',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Foley cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-FOLEY CATH',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-foley catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Foley Catheter',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-FOLEY CATHETER',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Foley Output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Fpley',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Ileoconduit',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-left nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Left Nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Left Nephrostomy Tube',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-LEFT PCN TUBE',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-L Nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-L Nephrostomy Tube',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-right nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-RIGHT Nephrouretero Stent Urine Output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-R nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-R Nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-R. Nephrostomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-R Nephrostomy Tube',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Rt Nephrectomy',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-stent',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-suprapubic',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Texas Cath',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Urine',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output-Urine Output',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine, R neph:',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|urine (void)',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine- void',
                'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine, void:'
            ) THEN 1
            WHEN cellpath ILIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|foley%'
                AND LOWER(cellpath) NOT LIKE '%pacu%'
                AND LOWER(cellpath) NOT LIKE '%or%'
                AND LOWER(cellpath) NOT LIKE '%ir%'
                THEN 1
            WHEN cellpath LIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Output%Urinary Catheter%' THEN 1
            WHEN cellpath LIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Output%Urethral Catheter%' THEN 1
            WHEN cellpath LIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urine Output (mL)%' THEN 1
            WHEN cellpath LIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Output%External Urethral%' THEN 1
            WHEN cellpath LIKE 'flowsheet|Flowsheet Cell Labels|I&O|Output (ml)|Urinary Catheter Output%' THEN 1
            ELSE 0
        END AS is_uo
    FROM eicu_crd.intakeoutput
)

-- Sum urine output in first 24h, with fallback to apacheapsvar.urine
, pivoted_uo_sum AS (
    SELECT
        patientunitstayid,
        SUM(cellvaluenumeric) AS urineoutput
    FROM uo_raw
    WHERE is_uo = 1
      AND cellvaluenumeric IS NOT NULL
      AND intakeoutputoffset > 0
      AND intakeoutputoffset <= 1440
    GROUP BY patientunitstayid
)

, merged_uo AS (
    SELECT
        p.patientunitstayid,
        COALESCE(uo.urineoutput, apache_uo.urine) AS uo_comb
    FROM eicu_crd.patient p
    LEFT JOIN pivoted_uo_sum uo ON p.patientunitstayid = uo.patientunitstayid
    LEFT JOIN (
        SELECT patientunitstayid, urine
        FROM eicu_crd.apacheapsvar
        WHERE urine > 0 AND urine IS NOT NULL
    ) apache_uo ON p.patientunitstayid = apache_uo.patientunitstayid
)

, urineoutput_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN uo_comb < 671 THEN 10
            WHEN uo_comb BETWEEN 671 AND 1426.99 THEN 5
            WHEN uo_comb BETWEEN 1427 AND 2543.99 THEN 1
            WHEN uo_comb BETWEEN 2544 AND 6896 THEN 0
            WHEN uo_comb > 6896 THEN 8
            ELSE NULL
        END AS urineoutput_oasis
    FROM merged_uo
)

-- ══════════════════════════════════════════════════════════════════
-- Elective Surgery — matching eicu-code logic
-- ══════════════════════════════════════════════════════════════════
, elective_surgery AS (
    SELECT
        pat.patientunitstayid,
        apache.electivesurgery AS electivesurgery1,
        CASE
            WHEN pat.unitadmitsource = 'Emergency Department' THEN 0
            ELSE 1
        END AS adm_elective1
    FROM eicu_crd.patient pat
    LEFT JOIN eicu_crd.apachepredvar apache
        ON pat.patientunitstayid = apache.patientunitstayid
)

, electivesurgery_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN electivesurgery1 = 0 THEN 6
            WHEN electivesurgery1 IS NULL THEN 6
            WHEN adm_elective1 = 0 THEN 6
            ELSE 0
        END AS electivesurgery_oasis
    FROM elective_surgery
)

-- ══════════════════════════════════════════════════════════════════
-- Ventilation — 3 sources (ventilation_events not in eicu-code repo)
-- ══════════════════════════════════════════════════════════════════
, merged_vent AS (
    SELECT
        p.patientunitstayid,
        -- apacheapsvar.intubated
        COALESCE(apsvar.intubated_flag, 0) AS vent_apsvar,
        -- apachepredvar.oobintubday1
        COALESCE(predvar.oobintub_flag, 0) AS vent_predvar,
        -- respiratorycare airway
        COALESCE(rc.vent_rc, 0) AS vent_rc
    FROM eicu_crd.patient p
    LEFT JOIN (
        SELECT patientunitstayid, 1 AS intubated_flag
        FROM eicu_crd.apacheapsvar WHERE intubated = 1
    ) apsvar ON p.patientunitstayid = apsvar.patientunitstayid
    LEFT JOIN (
        SELECT patientunitstayid, 1 AS oobintub_flag
        FROM eicu_crd.apachepredvar WHERE oobintubday1 = 1
    ) predvar ON p.patientunitstayid = predvar.patientunitstayid
    LEFT JOIN (
        SELECT patientunitstayid,
            CASE
                WHEN COUNT(airwaytype) >= 1 THEN 1
                WHEN COUNT(airwaysize) >= 1 THEN 1
                WHEN COUNT(airwayposition) >= 1 THEN 1
                WHEN COUNT(cuffpressure) >= 1 THEN 1
                WHEN COUNT(setapneatv) >= 1 THEN 1
                ELSE NULL
            END AS vent_rc
        FROM eicu_crd.respiratorycare
        WHERE respcarestatusoffset > 0 AND respcarestatusoffset <= 1440
        GROUP BY patientunitstayid
    ) rc ON p.patientunitstayid = rc.patientunitstayid
)

, vent_oasis AS (
    SELECT
        patientunitstayid,
        CASE
            WHEN vent_apsvar = 1 THEN 9
            WHEN vent_predvar = 1 THEN 9
            WHEN vent_rc = 1 THEN 9
            ELSE 0
        END AS vent_oasis
    FROM merged_vent
)

-- ══════════════════════════════════════════════════════════════════
-- Final assembly — matching eicu-code score_impute + score
-- ══════════════════════════════════════════════════════════════════
SELECT
    p.patientunitstayid,
    p.uniquepid,
    p.patienthealthsystemstayid,
    -- Total OASIS (imputed: NULL → 0)
    COALESCE(plos.pre_icu_los_oasis, 0)
    + COALESCE(ao.age_oasis, 0)
    + COALESCE(go.gcs_oasis, 0)
    + COALESCE(hr.heartrate_oasis, 0)
    + COALESCE(mo.map_oasis, 0)
    + COALESCE(rr.respiratoryrate_oasis, 0)
    + COALESCE(t.temperature_oasis, 0)
    + COALESCE(uo.urineoutput_oasis, 0)
    + COALESCE(vo.vent_oasis, 0)
    + COALESCE(eo.electivesurgery_oasis, 0)
    AS oasis,
    COALESCE(plos.pre_icu_los_oasis, 0) AS preiculos_score,
    COALESCE(ao.age_oasis, 0) AS age_score,
    COALESCE(go.gcs_oasis, 0) AS gcs_score,
    COALESCE(hr.heartrate_oasis, 0) AS heart_rate_score,
    COALESCE(mo.map_oasis, 0) AS mbp_score,
    COALESCE(rr.respiratoryrate_oasis, 0) AS resp_rate_score,
    COALESCE(t.temperature_oasis, 0) AS temp_score,
    COALESCE(uo.urineoutput_oasis, 0) AS urineoutput_score,
    COALESCE(vo.vent_oasis, 0) AS mechvent_score,
    COALESCE(eo.electivesurgery_oasis, 0) AS electivesurgery_score
FROM eicu_crd.patient p
LEFT JOIN pre_icu_los_data plos ON p.patientunitstayid = plos.patientunitstayid
LEFT JOIN age_oasis ao ON p.patientunitstayid = ao.patientunitstayid
LEFT JOIN gcs_oasis go ON p.patientunitstayid = go.patientunitstayid
LEFT JOIN heartrate_oasis hr ON p.patientunitstayid = hr.patientunitstayid
LEFT JOIN map_oasis mo ON p.patientunitstayid = mo.patientunitstayid
LEFT JOIN respiratoryrate_oasis rr ON p.patientunitstayid = rr.patientunitstayid
LEFT JOIN temperature_oasis t ON p.patientunitstayid = t.patientunitstayid
LEFT JOIN urineoutput_oasis uo ON p.patientunitstayid = uo.patientunitstayid
LEFT JOIN vent_oasis vo ON p.patientunitstayid = vo.patientunitstayid
LEFT JOIN electivesurgery_oasis eo ON p.patientunitstayid = eo.patientunitstayid
;
```
