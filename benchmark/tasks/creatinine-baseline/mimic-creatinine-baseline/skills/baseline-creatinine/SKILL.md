---
name: baseline-creatinine
description: Estimate baseline serum creatinine for AKI assessment. Use for KDIGO staging, AKI research, or renal function baseline establishment.
tier: validated
category: clinical
---

# Baseline Creatinine Estimation

Estimates the patient's baseline (pre-illness) serum creatinine, which is critical for accurate AKI staging. The true baseline is often unknown; this query uses a hierarchical approach.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- KDIGO AKI staging (requires baseline comparison)
- AKI research cohorts
- Chronic kidney disease identification
- Renal function trajectory analysis

## Baseline Determination Rules

The baseline creatinine is determined hierarchically:

1. **If lowest admission creatinine <= 1.1 mg/dL**: Use the lowest value (assumed normal)
2. **If patient has CKD diagnosis**: Use the lowest admission value (even if elevated)
3. **Otherwise**: Estimate baseline using MDRD equation assuming GFR = 75 mL/min/1.73m^2

## MDRD Estimation Formula

For patients without normal creatinine and without CKD, baseline is estimated:

**Male patients:**
```
scr_baseline = (75 / 186 / age^(-0.203))^(-1/1.154)
```

**Female patients:**
```
scr_baseline = (75 / 186 / age^(-0.203) / 0.742)^(-1/1.154)
```

This back-calculates creatinine assuming eGFR = 75 mL/min/1.73m^2 (lower limit of normal).

## CKD Identification

CKD is identified from ICD codes:
- **ICD-9**: 585 (Chronic kidney disease)
- **ICD-10**: N18 (Chronic kidney disease)

## Critical Implementation Notes

1. **Adults Only**: Query filters to age >= 18 (pediatric creatinine norms differ).

2. **MDRD Limitations**:
   - Less accurate in elderly, extremes of body size, or certain ethnicities
   - Assumes GFR = 75, which may underestimate for young healthy patients

3. **Admission Bias**: Using admission creatinine as baseline may underestimate for patients admitted already in AKI (AKI-on-admission).

4. **CKD May Be Coded Late**: ICD codes are assigned at discharge, so this technically uses future information. In most research this is acceptable.

5. **Missing Values**: If no creatinine measured during admission, baseline will be NULL.

6. **Race Coefficient**: The original MDRD had a race coefficient; this implementation does not use it, consistent with recent guidelines removing race from eGFR calculations.

## Alternative Baseline Methods

Other approaches used in literature (not implemented here):
1. **Outpatient creatinine**: Use pre-admission ambulatory values (requires linked outpatient data)
2. **Rolling minimum**: Lowest value in past 7-365 days
3. **First available**: First creatinine of admission (problematic if AKI present)
4. **Fixed MDRD**: Always use MDRD with assumed GFR (consistent but may miss true normal)

## References

- KDIGO Clinical Practice Guideline for Acute Kidney Injury. Kidney International Supplements. 2012.
- Siew ED et al. "Estimating baseline kidney function in hospitalized patients with impaired kidney function." Clinical Journal of the American Society of Nephrology. 2012;7(5):712-719.
