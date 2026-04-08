---
name: meld-score
description: Calculate MELD (Model for End-Stage Liver Disease) score for ICU patients. Use for liver disease severity assessment, transplant prioritization, or hepatology research.
tier: validated
category: clinical
---

# MELD Score Calculation

The Model for End-Stage Liver Disease (MELD) score predicts 3-month mortality in patients with liver disease. Originally developed for TIPS procedure prognostication, it is now the primary organ allocation criterion for liver transplantation in the US. The MELD-Na variant incorporates serum sodium for improved prediction.

## When to Use This Skill

- Liver disease severity assessment
- Transplant prioritization research
- Hepatology outcome studies
- Cirrhosis prognosis evaluation

## Score Components

MELD uses 4 laboratory values with logarithmic transformations:

| Component | Variable | Formula Weight | Floor | Ceiling |
|-----------|----------|---------------|-------|---------|
| Creatinine | Serum creatinine (mg/dL) | 0.957 × ln(Cr) | 1.0 | 4.0 (or if RRT) |
| Bilirubin | Total bilirubin (mg/dL) | 0.378 × ln(Bili) | 1.0 | — |
| INR | International Normalized Ratio | 1.120 × ln(INR) + 0.643 | 1.0 | — |
| Sodium | Serum sodium (mEq/L) | 137 - Na | 125 | 137 |

## Calculation Steps

1. **Component scores** (all values floored at 1.0 for logarithm):
   - Creatinine: `0.957 × ln(max(Cr, 1))` — capped at Cr=4 if RRT or Cr > 4
   - Bilirubin: `0.378 × ln(max(Bili, 1))`
   - INR: `1.120 × ln(max(INR, 1)) + 0.643`

2. **MELD Initial**: `round(Cr_score + Bili_score + INR_score, 1) × 10`
   - Capped at 40 if sum > 4

3. **Sodium adjustment** (MELD-Na, only if MELD Initial > 11):
   - Sodium score: `137 - max(min(Na, 137), 125)`
   - `MELD = MELD_Initial + 1.32 × Na_score - 0.033 × MELD_Initial × Na_score`
   - If MELD Initial ≤ 11: MELD = MELD Initial (no sodium adjustment)

## Critical Implementation Notes

1. **Creatinine Cap**: Patients on renal replacement therapy (RRT/dialysis) OR with creatinine > 4.0 are scored as creatinine = 4.0. This prevents extreme renal failure from dominating the score.

2. **INR Constant Term**: Unlike other components, INR scoring adds a constant 0.643 even when INR = 1 (ln(1) = 0). This means the minimum contribution from INR is always 0.643.

3. **Sodium Conditional**: The sodium adjustment is ONLY applied when MELD Initial > 11. Below this threshold, mild liver disease is not affected by hyponatremia.

4. **Score Range**: Theoretical minimum ~6 (all normal values), maximum 40 (hard cap).

5. **RRT Detection**: In MIMIC-IV, dialysis is detected from the `first_day_rrt` derived table, which checks for CRRT/IHD procedures in the first 24 hours.

6. **Missing Lab Values**: When a lab value is not available for a stay, the component defaults to its minimum contribution: ln(1) = 0. This means creatinine scores as 1.0, bilirubin scores as 1.0, INR scores as 1.0 (but still contributes the +0.643 constant), and sodium defaults to 137 (no adjustment). Include ALL ICU stays in the output, even those missing some or all lab values.

## Pre-computed Table

MIMIC-IV provides a pre-computed MELD table:

```sql
SELECT
    stay_id,
    meld,
    meld_initial,
    rrt,
    creatinine_max,
    bilirubin_total_max,
    inr_max,
    sodium_min
FROM mimiciv_derived.meld;
```

## Required Tables for Custom Calculation

- `mimiciv_icu.icustays` — ICU stay identifiers
- `mimiciv_derived.first_day_lab` — creatinine_max, bilirubin_total_max, inr_max, sodium_min
- `mimiciv_derived.first_day_rrt` — dialysis_present flag

## References

- Kamath PS et al. "A model to predict survival in patients with end-stage liver disease." Hepatology. 2001;33(2):464-470.
- Kim WR et al. "Hyponatremia and mortality among patients on the liver-transplant waiting list." N Engl J Med. 2008;359(10):1018-1026.
- Biggins SW et al. "Evidence-based incorporation of serum sodium concentration into MELD." Gastroenterology. 2006;130(6):1652-1660.
