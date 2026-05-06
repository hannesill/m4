# Operational Spec: Rolling Urine Output Rate

## Output Contract

Return one row per ICU stay and urine output measurement time. The key is
`stay_id, charttime`.

Required columns, in order:
`stay_id, charttime, weight, uo, urineoutput_6hr, urineoutput_12hr,
urineoutput_24hr, uo_mlkghr_6hr, uo_mlkghr_12hr, uo_mlkghr_24hr,
uo_tm_6hr, uo_tm_12hr, uo_tm_24hr`.

## Urine Output Events

Aggregate urine output volume to one value per `stay_id, charttime`. Use mL as
the unit. If multiple output records occur at the same measurement time for the
same stay, sum them. Apply the documented sign convention for returned irrigant:
returned irrigant decreases net urine output rather than increasing it.

## ICU Observation Boundaries

For elapsed-time calculations, define the ICU observation interval using the
first and last heart-rate charting events linked to the stay, not the raw ICU
admission and discharge timestamps.

For the first urine output measurement in a stay, elapsed time is the time from
the heart-rate-derived observation start to the urine output measurement time.
For later urine output measurements, elapsed time is the time from the previous
urine output measurement for that stay to the current measurement time.

## Rolling Windows

At each urine output measurement time, calculate rolling totals over 6-hour,
12-hour, and 24-hour windows. Sum both urine output volume and elapsed
observation time for measurements contributing to each window. The current
measurement interval contributes to the window.

Use the conventional whole-hour cutoffs for irregular charting:

- 6-hour window: include contributing measurements no more than 5 elapsed whole
  hours before the current measurement.
- 12-hour window: include contributing measurements no more than 11 elapsed
  whole hours before the current measurement.
- 24-hour window: include contributing measurements no more than 23 elapsed
  whole hours before the current measurement.

Store the rolling urine output totals in `urineoutput_6hr`,
`urineoutput_12hr`, and `urineoutput_24hr`. Store the summed elapsed time in
hours in `uo_tm_6hr`, `uo_tm_12hr`, and `uo_tm_24hr`.

## Weight Normalization

Use the positive charted weight interval covering the urine output measurement
time. A weight interval covers the measurement when the measurement occurs after
the interval start and at or before the interval end. If no positive covering
weight is available, keep `weight` null and set all rate columns to null.

## Rate Formula

For each window, calculate:

`urine output rate = rolling urine output volume / weight / rolling elapsed hours`

Only calculate a rate when the corresponding elapsed time is at least the full
window length: 6, 12, or 24 hours. Otherwise set that rate to null.

## Rounding and Missingness

Round `uo_mlkghr_*` columns to 4 decimal places. Round `uo_tm_*` columns to 2
decimal places. Preserve nulls for rates that cannot be calculated; do not
replace missing rates with zero. Numeric comparisons are tolerant to small
rounding differences of about 0.01.
