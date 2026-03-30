# Urine Output Rate

## What it is

Calculates rolling urine output rates (mL/kg/hr) over 6, 12, and 24-hour windows,
normalized by patient weight. Used for KDIGO AKI staging (urine output criterion)
and SOFA renal component.

This is the most data-engineering-intensive benchmark task: self-joins for rolling
windows, LAG-based time deltas, weight normalization, and conditional rate computation.

## The multi-step computation

1. **ICU time boundaries**: Define ICU stay period from first/last HR charting
   (itemid 220045), not from `icustays.intime/outtime` directly
2. **Time deltas**: LAG function computes minutes since the previous UO measurement;
   first measurement uses time since ICU intime
3. **Rolling window aggregation**: Self-join sums UO and elapsed time within each
   window (<=5h for 6hr, <=11h for 12hr, <=23h for 24hr, measured as hours between
   the summed measurement and the target charttime)
4. **Weight normalization**: Join to `weight_durations` for patient weight at each
   UO measurement time
5. **Minimum coverage**: Rate is only computed when sufficient time has elapsed
   (uo_tm_6hr >= 6, uo_tm_12hr >= 12, uo_tm_24hr >= 24)

## Data sources in MIMIC-IV

- **Urine output**: `mimiciv_derived.urine_output` (standard) or `mimiciv_icu.outputevents`
  with 12 urine-related itemids (raw)
- **Weight**: `mimiciv_derived.weight_durations` (standard) or `mimiciv_icu.chartevents`
  with itemids 226512, 224639 (raw)
- **ICU boundaries**: `mimiciv_icu.icustays` + `mimiciv_icu.chartevents` (itemid 220045)

## Why this tests different capabilities than severity scores

- **Complex temporal aggregation**: Self-join for rolling window sums (not simple
  GROUP BY or window function)
- **LAG-based time accounting**: Time since last measurement, not fixed intervals
- **Weight normalization**: Must join to weight table with time-interval overlap logic
- **Conditional output**: Rates are NULL when insufficient time coverage
- **Multiple rows per stay**: One row per UO charting event, with composite key
  (stay_id, charttime)
- **More data engineering than clinical concept**: Tests SQL fluency specifically

## Why standard vs raw

- **Standard**: Only `mimiciv_derived.urine_output_rate` is dropped. Agent uses
  `mimiciv_derived.urine_output` (pre-aggregated UO) and
  `mimiciv_derived.weight_durations` (pre-computed weight intervals).
- **Raw**: `urine_output_rate`, `urine_output`, and `weight_durations` are all dropped.
  Agent must extract UO from `mimiciv_icu.outputevents` (12 itemids, with sign-flip
  for itemid 227488) and compute weight from `mimiciv_icu.chartevents`.

## Subtleties to watch for

- The `tm` CTE uses HR chartevents (itemid 220045) for ICU boundaries, not icustays timestamps
- Rolling window cutoffs are <=5, <=11, <=23 hours (not <=6, <=12, <=24)
- The 24hr window includes ALL data in the self-join (no CASE filter for 24hr)
- Time is computed as DATE_DIFF in microseconds divided by constants (60000000 for minutes,
  3600000000 for hours)
- Item 227488 has inverted sign (GU irrigant return — negative values represent output)
- Missing weight → NULL rates (not zero)
- Rounding: ROUND(..., 4) for mL/kg/hr rates, ROUND(..., 2) for time columns
