-- ------------------------------------------------------------------
-- Title: Sepsis-3 Cohort Identification
-- Identifies sepsis patients using the Sepsis-3 consensus definition:
-- SOFA score >= 2 coinciding with suspected infection within a
-- 48h-before to 24h-after time window.
-- ------------------------------------------------------------------

-- Reference:
--    Singer M et al. "The Third International Consensus Definitions
--    for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.

-- Adapted from mimic-code sepsis3.sql
-- Returns one row per ICU stay (earliest matching infection event).

WITH sofa AS (
  SELECT
    stay_id,
    starttime,
    endtime,
    respiration_24hours AS respiration,
    coagulation_24hours AS coagulation,
    liver_24hours AS liver,
    cardiovascular_24hours AS cardiovascular,
    cns_24hours AS cns,
    renal_24hours AS renal,
    sofa_24hours AS sofa_score
  FROM mimiciv_derived.sofa
  WHERE
    sofa_24hours >= 2
), s1 AS (
  SELECT
    soi.subject_id,
    soi.stay_id,
    soi.ab_id,
    soi.antibiotic,
    soi.antibiotic_time,
    soi.culture_time,
    soi.suspected_infection,
    soi.suspected_infection_time,
    soi.specimen,
    soi.positive_culture,
    starttime,
    endtime,
    respiration,
    coagulation,
    liver,
    cardiovascular,
    cns,
    renal,
    sofa_score,
    CAST(sofa_score >= 2 AND suspected_infection = 1 AS INTEGER) AS sepsis3,
    ROW_NUMBER() OVER (PARTITION BY soi.stay_id ORDER BY suspected_infection_time NULLS FIRST, antibiotic_time NULLS FIRST, culture_time NULLS FIRST, endtime NULLS FIRST) AS rn_sus
  FROM mimiciv_derived.suspicion_of_infection AS soi
  INNER JOIN sofa
    ON soi.stay_id = sofa.stay_id
    AND sofa.endtime >= soi.suspected_infection_time - INTERVAL '48' HOUR
    AND sofa.endtime <= soi.suspected_infection_time + INTERVAL '24' HOUR
  WHERE
    NOT soi.stay_id IS NULL
)
SELECT
  subject_id,
  stay_id,
  antibiotic_time,
  culture_time,
  suspected_infection_time,
  endtime AS sofa_time,
  sofa_score,
  respiration,
  coagulation,
  liver,
  cardiovascular,
  cns,
  renal,
  sepsis3
FROM s1
WHERE
  rn_sus = 1
