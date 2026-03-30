# Suspicion of Infection

## What it is

Identifies suspected infection events by pairing systemic antibiotic administration
with culture collection within a defined time window. This operationalizes the infection
component of the Sepsis-3 consensus definition (Seymour et al. 2016).

## The matching logic

Each antibiotic prescription is matched to cultures in two directions:

1. **Culture before antibiotic (primary)**: Culture obtained within 72 hours before
   antibiotic start. If multiple cultures match, use the earliest.
2. **Culture after antibiotic (secondary)**: Culture obtained within 24 hours after
   antibiotic start. If multiple cultures match, use the earliest.

Culture-before-antibiotic takes precedence when both exist.

**Suspected infection time** = culture time (if culture came first) or antibiotic time
(if antibiotic came first).

## Data sources in MIMIC-IV

- **Antibiotics**: `mimiciv_derived.antibiotic` (standard) or `mimiciv_hosp.prescriptions`
  filtered for systemic routes (raw)
- **Cultures**: `mimiciv_hosp.microbiologyevents` — all specimen types
- **Positive culture**: `org_name` is non-null and `org_itemid != 90856` (the "NEGATIVE" sentinel)

## Why this tests different capabilities than severity scores

- **Temporal event matching**: Tests pairing events across two tables with asymmetric windows
- **One row per antibiotic**: Output cardinality is variable (not one per stay)
- **Composite key**: `subject_id` + `ab_id`, not `stay_id`
- **Dual timestamp handling**: Cultures may have `charttime` (precise) or only `chartdate`
  (day-level). The matching logic must handle both with different window arithmetic.
- **No numeric scoring**: Output is binary flags, not calculated values

## Why standard vs raw

- **Standard**: `mimiciv_derived.antibiotic` is available (pre-filtered for systemic routes)
- **Raw**: `antibiotic` table is dropped; agent must filter `mimiciv_hosp.prescriptions`
  for systemic routes, excluding topical routes (OU, OS, OD, AU, AS, AD, TP)

## Subtleties to watch for

- **DuckDB optimization**: OR conditions in JOIN clauses prevent DuckDB's IEJoin range-join
  optimization, causing ~18 min nested-loop scans. Split into two INNER JOINs with UNION ALL.
- **charttime vs chartdate**: Microbiology cultures sometimes only have dates (no times).
  When `charttime` is null, use `chartdate` with day-level matching (72h → 3 days, 24h → 1 day).
- **Antibiotic deduplication**: `ab_id` is a ROW_NUMBER per subject ordered by starttime,
  stoptime, antibiotic name. Each prescription gets a unique ID.
- **Culture positivity is not required**: Negative cultures count as suspected infection —
  the flag captures clinical suspicion, not confirmed infection.
- **stay_id may be NULL**: Antibiotics prescribed on the floor (not in ICU) have NULL stay_id.
- **Route filtering** (raw mode): Prescriptions table includes topical formulations. Must
  exclude routes: OU (both eyes), OS (left eye), OD (right eye), AU (both ears), AS (left ear),
  AD (right ear), TP (topical).
