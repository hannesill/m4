# Task: Calculate Urine Output Rate (Raw Tables)

All derived shortcut tables have been removed from the task database.
You must derive urine output, weight, ICU timing, and the requested rolling
rate concept from source clinical tables.

Calculate rolling urine output rates (mL/kg/hr) over 6, 12, and 24-hour
windows for each UO measurement time, normalized by patient weight,
following the MIT-LCP mimic-code urine_output_rate concept.

Rates are only computed when sufficient time has elapsed in each window
(>= 6h, >= 12h, >= 24h respectively). ICU time boundaries use the first
and last heart rate charting events, not raw admission times.

### Rounding

- Rate columns (`uo_mlkghr_*`): ROUND to 4 decimal places
- Time columns (`uo_tm_*`): ROUND to 2 decimal places

Output a CSV file to `{output_path}` with these exact columns:
stay_id, charttime, weight, uo, urineoutput_6hr, urineoutput_12hr,
urineoutput_24hr, uo_mlkghr_6hr, uo_mlkghr_12hr, uo_mlkghr_24hr,
uo_tm_6hr, uo_tm_12hr, uo_tm_24hr

One row per UO measurement time per ICU stay.
