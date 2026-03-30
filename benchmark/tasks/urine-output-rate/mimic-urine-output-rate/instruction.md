# Task: Calculate Urine Output Rate

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Calculate rolling urine output rates (mL/kg/hr) over 6, 12, and 24-hour
windows for each UO measurement time, normalized by patient weight.

### Approach

1. **Time boundaries**: Define the ICU stay period using the first and
   last heart rate charting events (not the raw ICU admission times)

2. **Time since last measurement**: For each UO event, compute time since
   the previous UO event (first measurement uses time since ICU start)

3. **Rolling window aggregation**: For each measurement at time T, sum
   all UO and elapsed time within:
   - **6-hour window**: measurements within the prior 5 hours
   - **12-hour window**: measurements within the prior 11 hours
   - **24-hour window**: measurements within the prior 23 hours

4. **Weight normalization**: Normalize by patient weight at measurement time

5. **Rate computation**: Rates are only computed when sufficient time has
   elapsed in the window:
   - `uo_mlkghr_6hr`: Only when `uo_tm_6hr >= 6` hours
   - `uo_mlkghr_12hr`: Only when `uo_tm_12hr >= 12` hours
   - `uo_mlkghr_24hr`: Only when `uo_tm_24hr >= 24` hours

   Formula: `urineoutput_Xhr / weight / uo_tm_Xhr`

### Rounding

- Rate columns (`uo_mlkghr_*`): ROUND to 4 decimal places
- Time columns (`uo_tm_*`): ROUND to 2 decimal places

Output a CSV file to `{output_path}` with these exact columns:
stay_id, charttime, weight, uo, urineoutput_6hr, urineoutput_12hr,
urineoutput_24hr, uo_mlkghr_6hr, uo_mlkghr_12hr, uo_mlkghr_24hr,
uo_tm_6hr, uo_tm_12hr, uo_tm_24hr

One row per UO measurement time per ICU stay.
