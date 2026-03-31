# Task: Calculate MELD Score (Raw Tables)

Only base tables are available — there are no pre-computed derived tables.

Calculate the MELD-Na (Model for End-Stage Liver Disease with sodium
adjustment) score for each ICU stay using data from the first 24 hours
of ICU admission (Kamath et al., Hepatology, 2001; Kim et al., NEJM, 2008).

Output a CSV file to `{output_path}` with these exact columns:
subject_id, hadm_id, stay_id, meld

One row per ICU stay.
