# Task: Calculate Norepinephrine-Equivalent Dose (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested vasopressor-equivalent dose calculation.

Calculate the norepinephrine-equivalent dose (NED) for each vasopressor
administration interval, enabling comparison across different vasopressor
agents.

Include only intervals where at least one vasopressor is active
(norepinephrine, epinephrine, phenylephrine, dopamine, vasopressin).
Exclude intervals with only inotropes (dobutamine, milrinone).

Round NED to 4 decimal places.

Output a CSV file to `{output_path}` with these exact columns:
stay_id, starttime, endtime, norepinephrine_equivalent_dose
