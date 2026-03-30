# Task: Calculate Norepinephrine-Equivalent Dose (Raw Tables)

You have access to a MIMIC-IV clinical database (DuckDB) at `{db_path}`.
It contains ICU patient data with schemas `mimiciv_hosp` and `mimiciv_icu`.
There are no pre-computed intermediate or derived tables. Compute directly
from raw tables such as `inputevents`.

Calculate the norepinephrine-equivalent dose (NED) for each vasopressor
administration interval, enabling comparison across different vasopressor
agents.

### Formula

```
NED = COALESCE(norepinephrine, 0)
    + COALESCE(epinephrine, 0)
    + COALESCE(phenylephrine / 10, 0)
    + COALESCE(dopamine / 100, 0)
    + COALESCE(vasopressin * 2.5 / 60, 0)
```

All doses must be in mcg/kg/min except vasopressin (units/hr, converted
in the formula). Round the result to 4 decimal places.

### Filtering

Include only intervals where at least one of the 5 vasopressors is
active (norepinephrine, epinephrine, phenylephrine, dopamine, vasopressin).
Exclude intervals with only inotropes (dobutamine, milrinone).

### Requirements

- Extract vasopressor administrations from raw medication tables and
  normalize rates to mcg/kg/min using patient weight
- One row per dose-change interval (multiple rows per ICU stay)
- Construct time intervals reflecting when combinations of active agents
  or their doses changed

Output a CSV file to `{output_path}` with these exact columns:
stay_id, starttime, endtime, norepinephrine_equivalent_dose
