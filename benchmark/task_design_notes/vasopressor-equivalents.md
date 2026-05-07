# Norepinephrine-Equivalent Vasopressor Dose

## What it is

Calculates a normalized vasopressor dose (norepinephrine-equivalent dose, NED) that enables
comparison across different vasopressor agents. Based on equivalence factors from Goradia et al.
2020 scoping review.

## The calculation

```
NED = norepinephrine + epinephrine + phenylephrine/10 + dopamine/100 + vasopressin*2.5/60
```

All doses are in mcg/kg/min except vasopressin (units/hr, converted in the formula).
Missing agents are COALESCEd to 0. Result is rounded to 4 decimal places.

## Data sources in MIMIC-IV

- **Consolidated rates**: `mimiciv_derived.vasoactive_agent` (standard) — provides per-interval
  dose rates for all vasoactive agents in a single table
- **Individual agents**: `mimiciv_derived.norepinephrine`, `epinephrine`, `dopamine`,
  `phenylephrine`, `vasopressin` — each extracted from `mimiciv_icu.inputevents` with
  weight-based unit conversion
- **Raw source**: `mimiciv_icu.inputevents` — contains all IV medication administrations
  with itemid-based identification

## Why this tests different capabilities than severity scores

- **Medication data navigation**: Must understand IV medication tables and itemid lookups
- **Unit conversion**: Vasopressin uses units/hr while others use mcg/kg/min
- **Multiple rows per stay**: Output has one row per dose-change interval, not one per stay
- **Composite key**: Identified by (stay_id, starttime), not just stay_id
- **Simple arithmetic, complex data**: The formula is trivial but the data pipeline is not

## Why standard vs raw

- **Standard**: `mimiciv_derived.vasoactive_agent` is available — agent applies the NED formula
  directly. Tests formula application and filtering.
- **Raw**: Vasopressor equivalent and task-relevant vasoactive derived tables are
  dropped. Agent must extract from `mimiciv_icu.inputevents` using correct
  itemids (221906 norepinephrine, 221289 epinephrine,
  221662 dopamine, 221749 phenylephrine, 222315 vasopressin), handle weight-based dose
  conversion, and construct time intervals.

## Subtleties to watch for

- Dobutamine and milrinone are in `vasoactive_agent` but excluded from NED (inotropes, not vasopressors)
- Filter: at least one of the 5 vasopressors must be non-null (rows with only dobutamine/milrinone excluded)
- The `vasoactive_agent` table already handles weight normalization and unit standardization
- `TRY_CAST(... AS DECIMAL)` is DuckDB-specific for precise rounding
