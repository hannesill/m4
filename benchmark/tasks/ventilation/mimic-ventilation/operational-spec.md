# Operational Spec: Ventilation Episodes

## Output Contract

Return one row per ventilation episode. The key is `stay_id,
ventilation_seq`.

Required columns, in order:
`stay_id, ventilation_seq, starttime, endtime, ventilation_status`.

Assign `ventilation_seq` as a row number within each stay ordered by
`starttime`.

## Observation Classification

Classify each charted respiratory support observation into at most one status.
Use this priority order when multiple indicators are present at the same time:

1. `Tracheostomy`
2. `InvasiveVent`
3. `NonInvasiveVent`
4. `HFNC`
5. `SupplementalOxygen`
6. `None`

Classify tracheostomy when a tracheostomy tube or tracheostomy mask is
documented. Classify invasive ventilation when an endotracheal tube or invasive
ventilator mode is documented. Classify non-invasive ventilation when a BiPAP,
CPAP, or NIV mask or mode is documented. Classify HFNC when high-flow nasal
cannula is documented. Classify supplemental oxygen for standard low-flow or
mask oxygen delivery devices. Classify `None` only when room air or no oxygen
support is explicitly documented.

Observations with no matching status are excluded before episode construction.

## Episode Construction

Within each stay and status, order observations by chart time. A new episode
starts when any of the following is true:

- it is the first classified observation for the stay;
- the status changes from the previous classified observation in the stay;
- the gap from the previous observation with the same status is at least 14
  hours.

For each episode, `starttime` is the earliest chart time in the episode.
`endtime` is the latest chart time reached by the episode; when the next
classified observation is within the 14-hour continuity window, use that next
observation time as the episode end boundary.

Exclude single-observation episodes where `starttime = endtime`.

## Missingness and Tie-Breakers

Do not emit rows for unclassified observations. If multiple status indicators
are present simultaneously, the priority order above is the tie-breaker. If
multiple observations have the same chart time and status, they belong to the
same episode boundary.
