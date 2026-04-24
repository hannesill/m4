# SOFA -- Sequential Organ Failure Assessment

## What it is

SOFA is a clinical score (0-24) that quantifies organ dysfunction across 6 systems.
Each component scores 0-4, with higher scores indicating greater dysfunction.
Introduced by Vincent et al. (1996) and adopted by the Sepsis-3 consensus (2016) as
the basis for sepsis diagnosis: SOFA >= 2 + suspected infection = sepsis.

## The 6 components (each scores 0-4)


| System                                  | 0       | 1       | 2                                    | 3                                              | 4                                            |
| --------------------------------------- | ------- | ------- | ------------------------------------ | ---------------------------------------------- | -------------------------------------------- |
| **Respiration** (PaO2/FiO2 mmHg)       | >= 400  | < 400   | < 300                                | < 200 + respiratory support                    | < 100 + respiratory support                  |
| **Coagulation** (Platelets x10^3/uL)   | >= 150  | < 150   | < 100                                | < 50                                           | < 20                                         |
| **Liver** (Bilirubin mg/dL)            | < 1.2   | 1.2-1.9 | 2.0-5.9                              | 6.0-11.9                                       | >= 12.0                                      |
| **Cardiovascular**                      | MAP>=70 | MAP<70  | Dopa<=5 or Dobutamine                | Dopa>5 or Epi<=0.1 or Norepi<=0.1             | Dopa>15 or Epi>0.1 or Norepi>0.1            |
| **CNS** (GCS)                          | 15      | 13-14   | 10-12                                | 6-9                                            | < 6                                          |
| **Renal** (Creatinine mg/dL or UO)     | < 1.2   | 1.2-1.9 | 2.0-3.4                              | 3.5-4.9 or UO<500 mL/day                      | >= 5.0 or UO<200 mL/day                     |


Vasopressor doses in mcg/kg/min. Total = sum of six components.

## Data sources in MIMIC-IV

- **Respiration**: `bg` (arterial PaO2/FiO2) + `ventilation` (vent status for score 3-4 interaction)
- **Coagulation**: `complete_blood_count` or `first_day_lab` (platelets)
- **Liver**: `enzyme` or `first_day_lab` (bilirubin)
- **Cardiovascular**: `vitalsign` or `first_day_vitalsign` (MAP) + `norepinephrine`, `epinephrine`, `dopamine`, `dobutamine` (vasopressor rates)
- **CNS**: `gcs` or `first_day_gcs` (Glasgow Coma Scale)
- **Renal**: `chemistry` or `first_day_lab` (creatinine) + `first_day_urine_output` (UO)
- Missing values are treated as normal (score 0)

## Why 12h vs 24h

Most ICU studies use the **first 24 hours** after admission. The **12-hour** variant
is clinically meaningful for early organ dysfunction assessment but non-standard --
it tests whether an agent can adapt to a legitimate parameter change.

Important: the renal UO criteria (< 500 mL/day, < 200 mL/day) require 24 hours of
data by definition. The 12h variant uses **creatinine only** for renal scoring.

## Why standard vs raw

- **Standard**: derived measurement tables (`mimiciv_derived.bg`, `vitalsign`, etc.) are available
- **Raw**: SOFA and task-relevant upstream derived tables are dropped, forcing
  the agent to aggregate from `chartevents`, `labevents`, `inputevents`, and
  `outputevents` directly

## Subtleties to watch for

- The respiratory criterion has a **ventilation interaction**: scores of 3-4 require
  invasive mechanical ventilation. PaO2/FiO2 is tracked separately for ventilated vs
  non-ventilated periods.
- The cardiovascular score=3 uses `rate_epinephrine <= 0.1` (not `> 0`). This means
  "any epinephrine present at dose <= 0.1 mcg/kg/min." NULL (not administered) falls
  through to lower scores. This is the mimic-code convention.
- **Vasopressor units** must be in mcg/kg/min. The derived vasopressor tables already
  provide this; raw computation from `inputevents` requires weight lookup.
- **Arterial blood gas only**: use specimens marked `ART.` for PaO2/FiO2.
- **Urine output validation**: the 24h SOFA uses `uo_tm_24hr >= 22 AND <= 30` to
  verify sufficient data coverage before computing daily UO rate.
- The `mimiciv_derived.sofa` and `first_day_sofa` tables are always dropped (they
  are the answer).
