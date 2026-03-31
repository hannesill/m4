# APACHE Groups -- APACHE IV Diagnosis Categorization

## What it is

APACHE IV admission diagnoses are free-text strings in `patient.apacheadmissiondx`
(e.g., "Sepsis, pulmonary", "CABG alone, coronary artery bypass grafting"). This
task maps each diagnosis to one of 21 clinically meaningful groups (Sepsis, ACS,
Trauma, CABG, etc.) using exact string matching.

## The 21 groups

ACS, ChestPainUnknown, CHF, CVOther, CardiacArrest, CABG, ValveDz, PNA,
RespMedOther, Asthma-Emphys, GIBleed, GIObstruction, CVA, Neuro, Coma,
Overdose, Sepsis, ARF, DKA, Trauma, Other.

## Data sources in eICU

- **`patient.apacheadmissiondx`**: Free-text APACHE IV admission diagnosis
- One row per ICU stay, all patients included

## Why this is interesting for benchmarking

- Tests domain knowledge: agent must know which diagnoses belong to which groups
- Pure classification task — no numerical calculation or complex joins
- ~100 specific diagnosis strings mapped to 21 groups
- eICU-only task (no MIMIC equivalent)

## Subtleties to watch for

- About 23K patients have NULL `apacheadmissiondx` — mapped to "Other"
- ~56K patients have diagnoses not in any specific group — also "Other"
- The eicu-code groups two separate CASE WHEN blocks for CVOther
  (cardiovascular medical + cardiovascular other)
- Diagnosis strings must be matched exactly (case-sensitive, full text)
