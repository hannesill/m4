# Reference SQL (matched-content control)

The following block is the public reference SQL used to construct the
ground truth for this task. It is provided verbatim, without procedural
prose, to test whether matched task-relevant content alone explains the
WITH-SKILL gain.

```sql
-- ------------------------------------------------------------------
-- Title: Glasgow Coma Scale (GCS) — first day minimum (eICU)
-- Matches eicu-code pivoted-gcs.sql logic, then aggregates to
-- minimum GCS in the first 24 hours per ICU stay.
-- ------------------------------------------------------------------

-- Reference:
--    Teasdale G, Jennett B. "Assessment of coma and impaired
--    consciousness. A practical scale." Lancet. 1974;2(7872):81-84.

-- Adapted from eicu-code pivoted-gcs.sql (BigQuery → DuckDB)

-- Step 1: Extract GCS components from nursecharting, matching
-- eicu-code filter logic exactly.
WITH nc AS (
    SELECT
        patientunitstayid,
        nursingchartoffset AS chartoffset,
        -- GCS Total from two label patterns
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
        END) AS gcs,
        -- Motor
        MIN(CASE
            WHEN nursingchartcelltypevallabel = 'Glasgow coma score'
             AND nursingchartcelltypevalname = 'Motor'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END) AS gcsmotor,
        -- Verbal
        MIN(CASE
            WHEN nursingchartcelltypevallabel = 'Glasgow coma score'
             AND nursingchartcelltypevalname = 'Verbal'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END) AS gcsverbal,
        -- Eyes
        MIN(CASE
            WHEN nursingchartcelltypevallabel = 'Glasgow coma score'
             AND nursingchartcelltypevalname = 'Eyes'
             AND TRY_CAST(nursingchartvalue AS NUMERIC) IS NOT NULL
                THEN CAST(nursingchartvalue AS NUMERIC)
            ELSE NULL
        END) AS gcseyes
    FROM eicu_crd.nursecharting
    WHERE nursingchartcelltypecat IN ('Scores', 'Other Vital Signs and Infusions')
    GROUP BY patientunitstayid, nursingchartoffset
)

-- Step 2: Validate GCS range (3-15), matching eicu-code
, ncproc AS (
    SELECT
        patientunitstayid,
        chartoffset,
        CASE WHEN gcs > 2 AND gcs < 16 THEN gcs ELSE NULL END AS gcs,
        gcsmotor,
        gcsverbal,
        gcseyes
    FROM nc
    WHERE gcs IS NOT NULL
       OR gcsmotor IS NOT NULL
       OR gcsverbal IS NOT NULL
       OR gcseyes IS NOT NULL
)

-- Step 3: First-day minimum — find the minimum GCS in first 24h
-- Window: -6h before to +24h after ICU admission (offset -360 to 1440)
, gcs_first_day AS (
    SELECT
        patientunitstayid,
        chartoffset,
        -- Use charted GCS total if available; else compute from components
        COALESCE(gcs, COALESCE(gcseyes, 4) + COALESCE(gcsmotor, 6) + COALESCE(gcsverbal, 5)) AS gcs_total,
        gcsmotor,
        gcsverbal,
        gcseyes,
        ROW_NUMBER() OVER (
            PARTITION BY patientunitstayid
            ORDER BY
                COALESCE(gcs, COALESCE(gcseyes, 4) + COALESCE(gcsmotor, 6) + COALESCE(gcsverbal, 5)),
                chartoffset
        ) AS rn
    FROM ncproc
    WHERE chartoffset >= -360
      AND chartoffset <= 1440
)

SELECT
    p.patientunitstayid,
    p.uniquepid,
    p.patienthealthsystemstayid,
    COALESCE(g.gcs_total, 15) AS gcs_min,
    COALESCE(g.gcsmotor, 6) AS gcs_motor,
    COALESCE(g.gcsverbal, 5) AS gcs_verbal,
    COALESCE(g.gcseyes, 4) AS gcs_eyes
FROM eicu_crd.patient p
LEFT JOIN gcs_first_day g
    ON p.patientunitstayid = g.patientunitstayid
    AND g.rn = 1
;
```
