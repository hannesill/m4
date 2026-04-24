---
name: oasis-score
description: Calculate OASIS (Oxford Acute Severity of Illness Score) for ICU patients. Use for mortality prediction with fewer variables than APACHE/SAPS, or when lab data is limited.
tier: validated
category: clinical
---

# OASIS Score Calculation

The Oxford Acute Severity of Illness Score (OASIS) is a parsimonious severity score that achieves comparable predictive accuracy to APACHE using fewer variables. It does not require laboratory values, making it useful when lab data is missing.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- Mortality prediction when lab data is incomplete
- Quick severity assessment with minimal variables
- Real-time severity scoring (no lab turnaround time)
- Research requiring a validated, simple severity metric
- Comparison with APACHE/SAPS scores

## Score Components (First 24 Hours)

| Variable | Range | Points |
|----------|-------|--------|
| Age | <24 to >=90 | 0-9 |
| Pre-ICU LOS | <10 min to >=18708 min | 0-5 |
| GCS | <=7 to >=15 | 0-10 |
| Heart Rate | <33 to >125 | 0-6 |
| Mean BP | <20.65 to >143.44 | 0-4 |
| Respiratory Rate | <6 to >44 | 0-10 |
| Temperature | <33.22 to >39.88 C | 0-6 |
| Urine Output | <671 to >6897 mL/day | 0-10 |
| Mechanical Ventilation | Yes/No | 0 or 9 |
| Elective Surgery | Yes/No | 0 for elective surgical admissions, 6 otherwise |

The OASIS total is the sum of the 10 component scores. Report the component
scores alongside the total so implementation differences are auditable.

## Critical Implementation Notes

1. **No Laboratory Values Required**: OASIS uses only vital signs, urine output, and administrative data - no labs needed.

2. **Pre-ICU LOS Scoring**: Time from hospital admission to ICU admission in minutes. Scoring is non-linear:
   - < 10.2 min: 5 points (immediate ICU)
   - 10.2-297 min: 3 points
   - 297-1440 min: 0 points (optimal)
   - 1440-18708 min: 2 points
   - > 18708 min: 1 point

3. **Mechanical Ventilation**: Binary flag - any invasive ventilation during first 24 hours scores 9 points.

4. **Elective Surgery**: Requires BOTH:
   - Elective admission type AND
   - Surgical service (identified from first service transfer)
   - **Scoring direction matters**: elective surgical admissions score **0**
     points; all other stays score **6** points

5. **Ventilation Flag Cannot Be Missing**: Unlike other components, ventilation defaults to 0 (no ventilation) if no data found.

6. **Mortality Probability**:
   ```
   oasis_prob = 1 / (1 + exp(-(-6.1746 + 0.1275 * oasis)))
   ```

## Benchmark Implementation Notes

- In the **standard** MIMIC task, use available first-day vitals, GCS, urine
  output, ventilation, admissions, and service-transfer information.
- In the **raw** MIMIC task, derive the same components from base ICU/hospital
  tables.
- In the **eICU** task, use eICU-native tables and keep the same scoring logic;
  do not assume MIMIC table names are present.

## Advantages Over APACHE/SAPS

- Simpler to calculate (10 variables vs 15-17)
- No laboratory data required
- Can be calculated earlier in admission
- Similar predictive accuracy

## References

- Johnson AEW, Kramer AA, Clifford GD. "A new severity of illness scale using a subset of Acute Physiology And Chronic Health Evaluation data elements shows comparable predictive accuracy." Critical Care Medicine. 2013;41(7):1711-1718.
