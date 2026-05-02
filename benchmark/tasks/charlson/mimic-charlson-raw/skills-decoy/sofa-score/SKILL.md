---
name: sofa-score
description: Calculate SOFA (Sequential Organ Failure Assessment) score for ICU patients. Use for sepsis severity assessment, organ dysfunction quantification, mortality prediction, or Sepsis-3 criteria evaluation.
tier: validated
category: clinical
---

# SOFA Score Calculation

The Sequential Organ Failure Assessment (SOFA) score quantifies organ dysfunction across 6 systems. Each component scores 0-4, with a total range of 0-24. Higher scores indicate greater organ dysfunction.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- User asks about SOFA score calculation
- Sepsis-3 criteria assessment (SOFA >= 2 indicates organ dysfunction)
- Mortality prediction or severity stratification
- Comparing organ dysfunction between cohorts
- Calculating delta-SOFA (change from baseline)

## Components and Scoring

| System | 0 | 1 | 2 | 3 | 4 |
|--------|---|---|---|---|---|
| **Respiration** (PaO2/FiO2 mmHg) | >= 400 | < 400 | < 300 | < 200 + respiratory support | < 100 + respiratory support |
| **Coagulation** (Platelets x10^3/uL) | >= 150 | < 150 | < 100 | < 50 | < 20 |
| **Liver** (Bilirubin mg/dL) | < 1.2 | 1.2-1.9 | 2.0-5.9 | 6.0-11.9 | >= 12.0 |
| **Cardiovascular** | No hypotension | MAP < 70 | Dopa <= 5 or Dob | Dopa > 5 or Epi <= 0.1 or Norepi <= 0.1 | Dopa > 15 or Epi > 0.1 or Norepi > 0.1 |
| **CNS** (GCS) | 15 | 13-14 | 10-12 | 6-9 | < 6 |
| **Renal** (Creatinine mg/dL or UO) | < 1.2 | 1.2-1.9 | 2.0-3.4 | 3.5-4.9 or UO < 500 | >= 5.0 or UO < 200 |

Note: Vasopressor doses are in mcg/kg/min. UO is urine output in mL/day.

## Required Tables for Custom Calculation

- `mimiciv_icu.icustays` - ICU stay identifiers
- `mimiciv_icu.chartevents` - vitals, GCS components, ventilation settings, weight
- `mimiciv_hosp.labevents` - blood gas, creatinine, bilirubin, platelets
- `mimiciv_icu.inputevents` - vasopressor infusions
- `mimiciv_icu.outputevents` - urine output

## Critical Implementation Notes

1. **Time Window**: The score uses the worst value in a 24-hour rolling window. SOFA calculated at hour 24 uses data from hours 0-24.

2. **Respiratory Score**: Requires interaction between PaO2/FiO2 ratio AND ventilation status:
   - Scores of 3 or 4 require mechanical ventilation
   - The lowest PaO2/FiO2 is tracked separately for ventilated vs non-ventilated periods
   - Important: The original SOFA publication does not explicitly define "respiratory support." In our SQL implementation, we define it as invasive mechanical ventilation only (vd.ventilation_status = 'InvasiveVent'). If you wish to include non-invasive ventilation (e.g., CPAP, BiPAP), modify the filter to: vd.ventilation_status IN ('InvasiveVent', 'NonInvasiveVent').

3. **FiO2 Sources**: FiO2 can come from blood gas measurement OR charted FiO2. When not documented, estimate from supplemental O2 device.

4. **Vasopressor Units**: All vasopressor doses must be in mcg/kg/min. Weight is often estimated from charted weight records when not directly documented.

5. **GCS in Sedated Patients**: For sedated/intubated patients, use pre-sedation GCS or assume normal (GCS=15). The verbal component may be 0 for intubated patients - this is handled specially.

6. **Arterial Blood Gas**: Use only arterial specimens (`specimen = 'ART.'`) for PaO2/FiO2.

7. **Missing Components**: Missing data is imputed as 0 (normal) in the final score. Document which components are missing; do not claim complete scores when data is absent. If you prefer to treat missing data as NA rather than 0, you will need to modify the SQL (remove the COALESCE(..., 0) wrapper). Statistically, it is more appropriate to treat missing values as missing and calculate SOFA scores after proper imputation.

8. **Urine Output Calculation**: Uses `uo_tm_24hr` to verify 24 hours of data available before calculating rate.

## References

- Vincent JL et al. "The SOFA (Sepsis-related Organ Failure Assessment) score to describe organ dysfunction/failure." Intensive Care Medicine. 1996;24(7):707-710.
- Vincent JL et al. Use of the SOFA score to assess the incidence of organ dysfunction/failure in intensive care units: results of a multicenter, prospective study. Working group on "sepsis-related problems" of the European Society of Intensive Care Medicine. Crit Care Med. 1998 Nov;26(11):1793-800.
- Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.
