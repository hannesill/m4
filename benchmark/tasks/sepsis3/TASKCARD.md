# Sepsis-3 Cohort Identification

## What it is

Identifies patients meeting the Sepsis-3 consensus definition (Singer et al. 2016):
SOFA score >= 2 coinciding with suspected infection within a defined time window.
This is the first **compositional** benchmark task — it combines two upstream derived
concepts rather than computing a score from raw measurements.

## The composition logic

1. **SOFA >= 2**: From `mimiciv_derived.sofa`, using 24-hour rolling worst values
2. **Suspected infection**: From `mimiciv_derived.suspicion_of_infection`
3. **Temporal match**: SOFA measurement endtime falls within 48 hours before to
   24 hours after the suspected infection time
4. **First event**: ROW_NUMBER picks the earliest matching infection event per stay

## Data sources in MIMIC-IV

- **SOFA scores**: `mimiciv_derived.sofa` — 24-hour rolling worst SOFA with components
- **Suspected infection**: `mimiciv_derived.suspicion_of_infection` — antibiotic-culture
  pairs with time window matching
- **Raw tables**: `mimiciv_icu.icustays` for stay identifiers

## Why this tests different capabilities than severity scores

- **Compositional reasoning**: Agent must combine two pre-computed concepts, not derive
  a score from raw measurements. Tests ability to understand and link derived tables.
- **Temporal join with asymmetric window**: The [-48h, +24h] window around suspected
  infection time requires interval-based join logic.
- **Boolean classification**: Output is a boolean flag (sepsis3), not a numeric score.
- **First-event extraction**: ROW_NUMBER with multi-column ordering for tie-breaking.
- **Subset output**: Only stays with both SOFA >= 2 and suspected infection appear,
  not all ICU stays.

## Why standard vs raw

- **Standard**: Only `mimiciv_derived.sepsis3` is dropped. Agent uses `mimiciv_derived.sofa`
  and `mimiciv_derived.suspicion_of_infection` directly. Tests composition logic.
- **Raw**: `sepsis3`, `sofa`, and `suspicion_of_infection` are all dropped. Agent must
  derive SOFA from its intermediate tables (bg, chemistry, vitalsign, gcs, ventilation,
  vasopressor tables, urine_output_rate) and suspicion of infection from
  `mimiciv_derived.antibiotic` + `mimiciv_hosp.microbiologyevents`. Lower-level
  intermediates remain available — the challenge is composing two complex concepts,
  not rebuilding them from scratch.

## Subtleties to watch for

- Baseline SOFA is assumed to be 0 (may over-classify chronic organ dysfunction)
- The `sepsis3` column is a boolean, TRUE when both sofa_score >= 2 AND suspected_infection = 1
- The SOFA time is the `endtime` of the SOFA measurement window, not the starttime
- ROW_NUMBER ordering: suspected_infection_time NULLS FIRST, antibiotic_time NULLS FIRST,
  culture_time NULLS FIRST, endtime NULLS FIRST
- Culture positivity is NOT required — clinical suspicion is sufficient
