-- Derived table: age
-- Source: MIT-LCP/mimic-code/mimic-iv/concepts/demographics/age.sql
-- Converted from BigQuery to DuckDB syntax
--
-- This query calculates patient age at hospital admission.

CREATE TABLE IF NOT EXISTS mimiciv_derived.age AS
SELECT
    ad.subject_id
    , ad.hadm_id
    , ad.admittime
    , pa.anchor_age
    , pa.anchor_year
    , pa.anchor_age + (EXTRACT(YEAR FROM ad.admittime) - pa.anchor_year) AS age
FROM hosp_admissions ad
INNER JOIN hosp_patients pa
    ON ad.subject_id = pa.subject_id
;
