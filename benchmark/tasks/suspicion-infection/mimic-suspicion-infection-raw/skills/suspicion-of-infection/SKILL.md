---
name: suspicion-of-infection
description: Identify suspected infection events using antibiotic administration plus culture timing. Use as a component of Sepsis-3 definition or for infection research.
tier: validated
category: clinical
---

# Suspicion of Infection

This concept identifies when clinicians suspected infection based on clinical actions: **systemic antibiotic administration** combined with **culture collection** within a defined time window. It operationalizes the infection component of the Sepsis-3 definition (Seymour et al. 2016).

## When to Use This Skill

- Building Sepsis-3 cohorts (infection component)
- Antibiotic stewardship research
- Time-to-treatment studies
- Infection onset timing
- Culture yield research

## Definition Logic

**Suspected infection** requires BOTH:
1. **Antibiotic administration** (systemic, not topical)
2. **Culture collection** within time window:
   - Culture obtained up to 72h BEFORE antibiotic, OR
   - Culture obtained up to 24h AFTER antibiotic

### Suspected Infection Time
The `suspected_infection_time` is defined as:
- The **culture time** if culture was obtained BEFORE antibiotic
- The **antibiotic time** if antibiotic was given BEFORE culture

This represents when infection was first clinically suspected.

### Culture Matching Logic

Each antibiotic is matched to cultures in two directions:

**Culture Before Antibiotic (Primary)**
- Culture obtained within 72 hours before antibiotic start
- If multiple cultures, uses the EARLIEST culture before the antibiotic

**Culture After Antibiotic (Secondary)**
- Culture obtained within 24 hours after antibiotic start
- If multiple cultures, uses the EARLIEST culture after the antibiotic

Priority: Culture-before-antibiotic takes precedence when both exist.

## Critical Implementation Notes

1. **One Row Per Antibiotic**: Each antibiotic prescription gets its own row, potentially matched to one culture. A single culture may be matched to multiple antibiotics.

2. **Culture Positivity Not Required**: Negative cultures still count as suspected infection — the flag captures clinical suspicion, not confirmed infection.

3. **All Culture Types Included**: Blood, urine, sputum, wound, CSF, etc. The `specimen` column identifies the type.

4. **Systemic Antibiotics Only**: Topical formulations (eye drops, ear drops, creams, ointments) must be excluded. The specific route codes vary by dataset.

## General Limitations

1. **Proxy for Clinical Suspicion**: Not all antibiotic + culture pairs represent true infection suspicion. Routine screening cultures (e.g., weekly surveillance) paired with prophylactic antibiotics may be misclassified as suspected infection.

2. **Time Window Is an Operationalization**: The 72h/24h windows are from the Seymour et al. operationalization. There is no biological basis for these specific cutoffs — they are pragmatic choices that balance sensitivity and specificity.

3. **Misses Antibiotic-Only or Culture-Only Events**: Patients treated empirically without cultures sent, or cultures obtained without subsequent antibiotics, will not be flagged.

4. **Does Not Distinguish Empiric vs Targeted Therapy**: The concept captures the initial antibiotic-culture pairing regardless of whether the antibiotic was empiric (before results) or targeted (after susceptibility).

## Dataset Availability

### MIMIC-IV

Suspicion of infection is available as a pre-computed derived table. Materialize with:

```bash
m4 init-derived mimic-iv          # All derived tables including suspicion_of_infection
```

```sql
SELECT
    subject_id,
    stay_id,
    hadm_id,
    ab_id,                     -- Unique antibiotic ID per patient
    antibiotic,                -- Antibiotic name
    antibiotic_time,           -- When antibiotic started
    suspected_infection,       -- 1 if meets criteria, 0 otherwise
    suspected_infection_time,  -- Onset time of suspected infection
    culture_time,              -- When culture was obtained
    specimen,                  -- Culture specimen type
    positive_culture           -- 1 if culture positive, 0 if negative
FROM mimiciv_derived.suspicion_of_infection;
```

BigQuery users already have this table via `physionet-data.mimiciv_derived.suspicion_of_infection` without running `init-derived`.

**MIMIC-IV implementation details:**
- The derived tables originate from the [MIT-LCP mimic-code](https://github.com/MIT-LCP/mimic-code) repository. The full SQL query is in `scripts/mimic-iv.sql`.
- Antibiotics sourced from `mimiciv_derived.antibiotic` (which filters the `prescriptions` table for systemic routes, excluding topical routes: OU, OS, OD, AU, AS, AD, TP, and topical formulations like creams, gels, ophthalmic ointments).
- Cultures from `mimiciv_hosp.microbiologyevents`. Positive culture identified by non-null `org_name` excluding itemid 90856 ("NEGATIVE").
- `stay_id` is populated when antibiotic timing overlaps with an ICU stay. May be NULL for floor patients.
- **Chart dates vs times**: Microbiology cultures sometimes only have dates (not times). When `charttime` is null, the query falls back to `chartdate` with day-level matching (72h becomes 3 days, 24h becomes 1 day).

**MIMIC-IV limitations:**
- Prescription duplication: each ICU stay in a hospitalization gets a copy of all prescriptions for that admission, which the query handles via unique `ab_id` per patient.
- Antibiotic route filtering relies on MIMIC's route coding. Miscoded routes could include topical antibiotics or exclude systemic ones.

### eICU

Suspicion of infection is **not pre-computed** in eICU. Both components must be derived from raw tables:

| Component | eICU Table | Columns | Notes |
|-----------|-----------|---------|-------|
| Antibiotics | `medication` | `drugname`, `routeadmin`, `drugstartoffset`, `drugstopoffset` | Free-text `drugname`; `drugstartoffset` in minutes from unit admission |
| Cultures | `microlab` | `culturetakenoffset`, `culturesite`, `organism` | `culturetakenoffset` in minutes from unit admission; positive culture = non-null `organism` |

**eICU limitations:**
- **Center variability in missingness**: Medication documentation and culture practices vary substantially across the 208 hospitals. Some sites have near-complete medication records; others have significant gaps. This non-random missingness affects infection identification rates.
- **Medication naming**: `drugname` is free-text and varies across sites. The same antibiotic may appear as "Vancomycin", "VANCOMYCIN", "vancomycin 1g IV", etc. Building a reliable antibiotic identification filter requires extensive text matching and validation.
- **Route coding**: `routeadmin` also varies by site. Excluding topical routes requires site-aware filtering.
- **Offset-based timing**: Both `drugstartoffset` and `culturetakenoffset` are in minutes from unit admission (not absolute timestamps). The antibiotic-culture pairing logic must use offset arithmetic rather than datetime comparisons.
- **No upstream antibiotic table**: Unlike MIMIC (which has a derived `antibiotic` table that pre-filters systemic antibiotics), eICU requires building the antibiotic filtering from scratch.

An eICU script is not yet available.

## Example: Infection Events Per Patient

```sql
SELECT
    subject_id,
    COUNT(*) AS n_suspected_infections,
    SUM(positive_culture) AS n_positive_cultures
FROM mimiciv_derived.suspicion_of_infection
WHERE suspected_infection = 1
GROUP BY subject_id
ORDER BY n_suspected_infections DESC;
```

## Example: Most Common Antibiotics in Suspected Infection

```sql
SELECT
    antibiotic,
    COUNT(*) AS n_prescriptions,
    SUM(positive_culture) AS n_positive,
    ROUND(AVG(positive_culture), 2) AS positive_rate
FROM mimiciv_derived.suspicion_of_infection
WHERE suspected_infection = 1
GROUP BY antibiotic
ORDER BY n_prescriptions DESC
LIMIT 20;
```

## Related Skills

- [sepsis-3-cohort](../sepsis-3-cohort/SKILL.md) — Combines this concept with SOFA >= 2 for Sepsis-3 identification
- [sofa-score](../sofa-score/SKILL.md) — Organ dysfunction component of Sepsis-3
- [sirs-criteria](../sirs-criteria/SKILL.md) — Historical inflammatory response criteria (pre-Sepsis-3)

## References

- Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.
- Seymour CW et al. "Assessment of Clinical Criteria for Sepsis." JAMA. 2016;315(8):762-774.
