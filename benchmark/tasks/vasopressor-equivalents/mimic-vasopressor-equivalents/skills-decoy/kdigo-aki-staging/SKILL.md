---
name: kdigo-aki-staging
description: Calculate KDIGO AKI (Acute Kidney Injury) staging for ICU patients using creatinine and urine output criteria. Use for nephrology research, AKI outcome studies, or renal function monitoring.
tier: validated
category: clinical
---

# KDIGO AKI Staging

The Kidney Disease: Improving Global Outcomes (KDIGO) criteria define Acute Kidney Injury (AKI) stages based on serum creatinine changes and/or urine output reduction.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- AKI incidence and outcome studies
- Renal function trajectory analysis
- CRRT initiation studies
- Drug-induced nephrotoxicity research
- ICU quality metrics

## AKI Staging Criteria

### Creatinine-Based Criteria
| Stage | Creatinine Criterion |
|-------|---------------------|
| 1 | >= 1.5x baseline within 7 days OR >= 0.3 mg/dL increase within 48h |
| 2 | >= 2.0x baseline |
| 3 | >= 3.0x baseline OR >= 4.0 mg/dL with acute increase OR RRT initiation |

### Urine Output-Based Criteria
| Stage | Urine Output Criterion |
|-------|----------------------|
| 1 | < 0.5 mL/kg/h for 6-12 hours |
| 2 | < 0.5 mL/kg/h for >= 12 hours |
| 3 | < 0.3 mL/kg/h for >= 24 hours OR anuria for >= 12 hours |

**Final AKI Stage** = MAX(creatinine stage, urine output stage, CRRT stage)

## Critical Implementation Notes

1. **Baseline Creatinine**: Uses the lowest creatinine in the past 7 days as the baseline. This may underestimate AKI if patient was already in AKI on admission.

2. **48-Hour Window**: The >= 0.3 mg/dL acute increase criterion uses the lowest creatinine in the past 48 hours specifically.

3. **Stage 3 with Cr >= 4.0**: Requires EITHER:
   - An acute increase >= 0.3 mg/dL within 48h, OR
   - An increase >= 1.5x baseline

4. **Urine Output Timing**: UO criteria require the patient to be in ICU for at least 6 hours before staging (KDIGO definition). Earlier times get stage 0.

5. **Weight for UO Calculation**: Use documented or estimated patient weight from available charted weight records. Weight estimation methods vary.

6. **CRRT as Stage 3**: Any patient on CRRT is automatically Stage 3 AKI.

7. **Smoothed Stage**: `aki_stage_smoothed` carries forward the maximum stage from the past 6 hours to reduce fluctuation between creatinine/UO measurements.

8. **Time Series Data**: AKI is calculated at every creatinine/UO measurement time, not just once per admission.

## References

- KDIGO Clinical Practice Guideline for Acute Kidney Injury. Kidney International Supplements. 2012;2(1):1-138.
- Kellum JA, Lameire N. "Diagnosis, evaluation, and management of acute kidney injury: a KDIGO summary." Critical Care. 2013;17(1):204.
