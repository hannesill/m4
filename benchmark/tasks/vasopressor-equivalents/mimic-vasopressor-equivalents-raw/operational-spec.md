# Operational Spec: Norepinephrine-Equivalent Dose

## Output Contract

Return one row per ICU stay and vasopressor dose interval. The key is
`stay_id, starttime`.

Required columns, in order:
`stay_id, starttime, endtime, norepinephrine_equivalent_dose`.

Only include intervals where at least one vasopressor is active.

## Eligible Agents

Include norepinephrine, epinephrine, phenylephrine, dopamine, and vasopressin.
Exclude intervals where only inotropes such as dobutamine or milrinone are
active. If an excluded inotrope overlaps an eligible vasopressor, ignore the
inotrope in the equivalence calculation.

## Interval Construction

Construct medication intervals over which the active agent set and dose rates
are constant. When multiple agents overlap, split intervals at every start or
stop boundary so each output row represents one constant concurrent exposure
state.

Use `starttime` and `endtime` as the interval boundaries. Do not emit intervals
with no eligible vasopressor exposure.

If more than one source row resolves to the same `stay_id, starttime, endtime`
interval, emit one output row for that interval and use the maximum calculated
norepinephrine-equivalent dose.

## Dose Units

Normalize catecholamine doses to mcg/kg/min. Use positive charted weight when a
rate requires weight normalization. Treat missing agent-specific rates as zero
in the final sum.

Vasopressin is charted in units per hour; convert it to the norepinephrine
equivalent scale with the formula below.

## Formula

Calculate:

`norepinephrine_equivalent_dose = norepinephrine + epinephrine +
phenylephrine / 10 + dopamine / 100 + vasopressin * 2.5 / 60`

Round `norepinephrine_equivalent_dose` to 4 decimal places. Numeric comparisons
are tolerant to small rounding differences of about 0.01.
