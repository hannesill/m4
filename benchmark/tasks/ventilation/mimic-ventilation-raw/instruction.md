# Task: Classify Ventilation Status (Raw Tables)

The target table and task-relevant upstream derived tables have been removed.
Other non-target derived tables may still be present; do not use them as a
shortcut for the requested ventilation classification.

Classify ventilation status from charting data and group consecutive
observations into ventilation episodes for each ICU stay, following
the MIT-LCP mimic-code ventilation concept definition.

Categories (in priority order): Tracheostomy, InvasiveVent,
NonInvasiveVent, HFNC, SupplementalOxygen, None.

Exclude single-observation episodes (starttime = endtime) and
observations with no classification.

`ventilation_seq` = ROW_NUMBER() within each stay, ordered by starttime.

Output a CSV file to `{output_path}` with these exact columns:
stay_id, ventilation_seq, starttime, endtime, ventilation_status

One row per ventilation episode. Multiple rows per ICU stay.
