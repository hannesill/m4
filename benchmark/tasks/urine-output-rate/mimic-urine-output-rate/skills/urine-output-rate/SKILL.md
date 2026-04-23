---
name: urine-output-rate
description: Calculate rolling urine output rates (mL/kg/hr) over 6/12/24-hour windows for ICU patients. Use for KDIGO AKI staging (urine output criterion) or SOFA renal component.
tier: validated
category: clinical
---

# Urine Output Rate

Calculates weight-normalized urine output rates over rolling 6, 12, and 24-hour windows. These rates are used for KDIGO AKI staging (oliguria criterion: UO < 0.5 mL/kg/hr for >= 6 hours) and the SOFA renal component.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- KDIGO AKI staging (urine output criterion)
- SOFA renal component computation
- Fluid balance studies
- Oliguria detection and monitoring
- Renal function assessment in critically ill patients

## Computation Methodology

### 1. Urine Output Aggregation

The intermediate table `mimiciv_derived.urine_output` aggregates raw output events per (stay_id, charttime) from `mimiciv_icu.outputevents`.

**Urine output itemids** (MIMIC-IV):
- 226559, 226560, 226561, 226584, 226563, 226564, 226565, 226567, 226557, 226558, 227488, 227489

**Sign convention**: Itemid 227488 (GU irrigant return) has inverted sign — positive values are multiplied by -1.

### 2. ICU Time Boundaries

ICU stay boundaries are derived from heart rate charting (itemid 220045) rather than `icustays.intime/outtime`:

```sql
SELECT stay_id, MIN(charttime) AS intime_hr, MAX(charttime) AS outtime_hr
FROM mimiciv_icu.icustays ie
INNER JOIN mimiciv_icu.chartevents ce
  ON ie.stay_id = ce.stay_id AND ce.itemid = 220045
  AND ce.charttime > ie.intime - INTERVAL '1' MONTH
  AND ce.charttime < ie.outtime + INTERVAL '1' MONTH
GROUP BY ie.stay_id
```

### 3. Time Delta Computation

LAG function computes time since the previous UO measurement:
- **First measurement**: Minutes from `intime_hr` to first charttime
- **Subsequent**: Minutes from previous charttime to current charttime

### 4. Rolling Window Aggregation

Self-join computes rolling sums. For each UO measurement at time T, include all prior measurements within the window:

| Window | Include measurements where | Hour cutoff |
|--------|---------------------------|-------------|
| 6-hour | `DATE_DIFF(hours) <= 5` | <= 5h |
| 12-hour | `DATE_DIFF(hours) <= 11` | <= 11h |
| 24-hour | All in self-join range | No filter |

The self-join condition bounds the outer range: `io.charttime <= iosum.charttime + INTERVAL '23' HOUR`.

Both `urineoutput` (mL) and `tm_since_last_uo` (minutes → hours) are summed within each window.

### 5. Weight Normalization

Patient weight comes from `mimiciv_derived.weight_durations`, joined with temporal overlap:
```sql
LEFT JOIN weight_durations wd
  ON ur.stay_id = wd.stay_id
  AND ur.charttime > wd.starttime
  AND ur.charttime <= wd.endtime
  AND wd.weight > 0
```

### 6. Minimum Coverage Rules

Rates are only computed when sufficient observation time exists:

| Rate Column | Minimum `uo_tm` Required |
|-------------|--------------------------|
| `uo_mlkghr_6hr` | `uo_tm_6hr >= 6` hours |
| `uo_mlkghr_12hr` | `uo_tm_12hr >= 12` hours |
| `uo_mlkghr_24hr` | `uo_tm_24hr >= 24` hours |

Formula: `rate = urineoutput_Xhr / weight / uo_tm_Xhr`

### 7. Rounding

- Rate columns (`uo_mlkghr_*`): ROUND to 4 decimal places
- Time columns (`uo_tm_*`): ROUND to 2 decimal places

## Critical Implementation Notes

1. **Self-join, not window function**: The rolling window uses a self-join (not ROWS BETWEEN), because observations are irregularly spaced in time.

2. **Hour cutoffs are off-by-one**: The 6hr window uses <= 5 hours, 12hr uses <= 11 hours. This is because the current measurement's own `tm_since_last_uo` is included in the sum, adding up to the full window.

3. **Missing weight**: If no weight is available, all rate columns are NULL (not zero).

4. **Time units**: DATE_DIFF uses microseconds for precision: divide by 60000000 for minutes, 3600000000 for hours.

5. **Output cardinality**: Multiple rows per stay (one per UO charting event). Key is (stay_id, charttime).

## Source Tables

- `mimiciv_derived.urine_output` — Aggregated UO per charttime
- `mimiciv_derived.weight_durations` — Patient weight intervals
- `mimiciv_icu.outputevents` — Raw UO events (for raw mode)
- `mimiciv_icu.chartevents` — HR for ICU boundaries, weight for raw mode
- `mimiciv_icu.icustays` — ICU stay identifiers

## References

- KDIGO Clinical Practice Guideline for Acute Kidney Injury. Kidney Int Suppl. 2012;2(1):1-138.
- Kellum JA et al. "Classifying AKI by Urine Output versus Serum Creatinine Level." JASN. 2015;26(9):2231-2238.
