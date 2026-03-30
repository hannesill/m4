# Task: Classify Ventilation Status

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp`, `mimiciv_icu`,
and pre-computed intermediate tables in `mimiciv_derived`.

Classify ventilation status from charting data and group consecutive
observations into ventilation episodes for each ICU stay, following
the MIT-LCP mimic-code ventilation concept definition.

### Ventilation Categories

Classify each charting observation into one of these categories, in
priority order (highest first):

| Priority | Category | Description |
|----------|----------|-------------|
| 1 | Tracheostomy | Patient has a tracheostomy tube or trach mask |
| 2 | InvasiveVent | Endotracheal tube present, or any invasive ventilator mode charted |
| 3 | NonInvasiveVent | BiPAP or CPAP mask, or non-invasive ventilator modes |
| 4 | HFNC | High-flow nasal cannula |
| 5 | SupplementalOxygen | Standard oxygen delivery devices (nasal cannula, non-rebreather, face tent, etc.) |
| 6 | None | No supplemental oxygen |

Classification is based on the O2 delivery device and ventilator mode
documented in charting data. When multiple indicators are present, the
highest-priority category wins.

### Episode Detection

Group individual observations into episodes using these rules:

1. **New episode starts when**:
   - First observation for a stay
   - Gap of >= 14 hours between consecutive same-status observations
   - Ventilation status changes from the previous observation

2. **14-hour gap**: The gap detection compares consecutive observations
   partitioned by `(stay_id, ventilation_status)`, not just `stay_id`

3. **Episode boundaries**:
   - `starttime` = earliest charttime in the episode
   - `endtime` = latest charttime in the episode

4. **Exclude single-observation episodes**: Filter out episodes where
   starttime equals endtime

5. **Exclude NULL status**: Observations with no classification are dropped

### Output

`ventilation_seq` = ROW_NUMBER() within each stay, ordered by starttime.

Output a CSV file to `{output_path}` with these exact columns:
stay_id, ventilation_seq, starttime, endtime, ventilation_status

One row per ventilation episode. Multiple rows per ICU stay.
