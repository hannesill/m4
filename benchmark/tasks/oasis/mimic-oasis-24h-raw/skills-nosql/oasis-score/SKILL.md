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

OASIS sums 10 component scores. The cutoffs below are aligned with the
M4Bench/MIMIC labels, which follow the public MIMIC implementation adapted
from Johnson AEW et al. (*Crit Care Med* 2013, Table 2). For min/max-bound
continuous variables, use the MIMIC evaluation order shown below because
first-match ordering affects component labels when both low and high extremes
occur in the first 24 h.

### Pre-ICU Length of Stay

| Range (hours) | In minutes | Score |
|---|---|---|
| < 0.17 | < 10.2 | 5 |
| 0.17 – 4.94 | 10.2 – 296.4 | 3 |
| 4.95 – 24.00 | 297.0 – 1440.0 | 0 |
| 24.01 – 311.80 | 1440.6 – 18708.0 | 2 |
| > 311.80 | > 18708 | 1 |

### Age (years)

| Range | Score |
|---|---|
| < 24 | 0 |
| 24 – 53 | 3 |
| 54 – 77 | 6 |
| 78 – 89 | 9 |
| ≥ 90 | 7 |

### Glasgow Coma Score (worst observation)

| Range | Score |
|---|---|
| 3 – 7 | 10 |
| 8 – 13 | 4 |
| 14 | 3 |
| 15 | 0 |

### Heart Rate (min^-1)

| Evaluation order | Bin | Score |
|---|---|---|
| 1 | max > 125 | 6 |
| 2 | min < 33 | 4 |
| 3 | max 107-125 | 3 |
| 4 | max 89-106 | 1 |
| 5 | otherwise | 0 |

### Mean Arterial Pressure (mmHg)

| Evaluation order | Bin | Score |
|---|---|---|
| 1 | min < 20.65 | 4 |
| 2 | min 20.65-50.99 | 3 |
| 3 | max > 143.44 | 3 |
| 4 | min 51-61.32 | 2 |
| 5 | otherwise | 0 |

### Respiratory Rate (min^-1)

| Evaluation order | Bin | Score |
|---|---|---|
| 1 | min < 6 | 10 |
| 2 | max > 44 | 9 |
| 3 | max 31-44 | 6 |
| 4 | max 23-30 | 1 |
| 5 | min < 13 | 1 |
| 6 | otherwise | 0 |

### Temperature (deg C)

| Evaluation order | Bin | Score |
|---|---|---|
| 1 | max > 39.88 | 6 |
| 2 | min or max 33.22-35.93 | 4 |
| 3 | min < 33.22 | 3 |
| 4 | min 35.94-36.39 | 2 |
| 5 | max 36.89-39.88 | 2 |
| 6 | otherwise | 0 |

### Urine Output (mL/day)

| Evaluation order | Range | Score |
|---|---|---|
| 1 | < 671.09 | 10 |
| 2 | > 6896.80 | 8 |
| 3 | 671.09-1426.99 | 5 |
| 4 | 1427.00-2544.14 | 1 |
| 5 | otherwise | 0 |

### Mechanical Ventilation

| Status | Score |
|---|---|
| No | 0 |
| Yes (any invasive ventilation in 24 h) | 9 |

### Elective Surgery

| Status | Score |
|---|---|
| Elective admission AND surgical service | 0 |
| All other admissions | 6 |

The OASIS total is the sum of the 10 component scores. Report the component
scores alongside the total so implementation differences are auditable.

## Direction-aware Scoring (MIMIC labels)

For MIMIC OASIS tasks, follow the M4Bench/MIMIC SQL evaluation order in the
tables above. This ordering is intentionally dataset-specific: if both a low
and high extreme occur in the same first-24h window, the first matching row in
the component table wins.

Key conflict rules for MIMIC labels:

- Heart rate prioritizes severe tachycardia (`max > 125`, 6 points) before
  severe bradycardia (`min < 33`, 4 points).
- MAP checks low MAP bins first, then high MAP (`max > 143.44`), then assigns
  low-normal/normal scores.
- Respiratory rate checks severe low RR first, then high RR bins, then mild low
  RR.
- Temperature prioritizes fever (`max > 39.88`, 6 points) before low-temperature
  bins.
- Urine output uses the exact MIMIC boundaries shown above.

GCS uses the worst (minimum) value only. Pre-ICU LOS, Age, Urine Output,
Mechanical Ventilation, and Elective Surgery are scalar — no min/max
distinction.

## Critical Implementation Notes

1. **No Laboratory Values Required**: OASIS uses only vital signs, urine
   output, and administrative data — no labs needed.

2. **Mechanical Ventilation**: Any invasive ventilation during the first
   24 hours scores 9 points; otherwise 0.

3. **Elective Surgery**: Requires BOTH an elective admission type AND a
   surgical service assignment (identified from the first service
   transfer). Scoring direction matters: elective surgical admissions
   score **0** points; all other stays score **6** points.

4. **Missing Data Handling**: Per task instruction, treat missing data
   as normal (score 0). When a component cannot be computed because the
   underlying observation is absent, score that component as 0 before
   summing. Output ALL ICU stays in the result, even those missing some
   or all source measurements.
   - Special case: the ventilation indicator is binary (yes/no) — absence
     of any ventilation record is interpreted as "no ventilation",
     contributing 0 points (not missing).

## Mortality Probability

OASIS predicts in-hospital mortality through a logistic model
(Johnson et al. 2013):

```
oasis_prob = 1 / (1 + exp(-(-6.1746 + 0.1275 * oasis)))
```

This probability is informational only and is not required by the M4Bench
output schema for this task.

## Source Data Required

OASIS requires the following clinical/administrative data per ICU stay:

- ICU admission and discharge times; hospital admission time (for pre-ICU LOS)
- Admission type (elective vs non-elective)
- Service or specialty assignment at the time of ICU admission (to identify
  surgical admissions)
- Patient age at admission
- First 24-hour vital signs: heart rate (min, max), mean arterial pressure
  (min, max), respiratory rate (min, max), temperature (min, max)
- First 24-hour Glasgow Coma Score (worst observation)
- First 24-hour urine output total
- Invasive mechanical ventilation status during the first 24 hours

## Advantages Over APACHE/SAPS

- Simpler to calculate (10 variables vs 15-17)
- No laboratory data required
- Can be calculated earlier in admission
- Similar predictive accuracy

## References

- Johnson AEW, Kramer AA, Clifford GD. "A new severity of illness scale using a subset of Acute Physiology And Chronic Health Evaluation data elements shows comparable predictive accuracy." *Critical Care Medicine*. 2013;41(7):1711-1718.
