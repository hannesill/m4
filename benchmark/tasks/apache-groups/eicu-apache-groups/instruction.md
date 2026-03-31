# Task: Map APACHE IV Diagnosis Groups (eICU)

You have access to an eICU Collaborative Research Database (DuckDB) at `{db_path}`.
It contains ICU patient data from 208 US hospitals in the `main` schema.
There are no pre-computed derived tables — you must work from raw tables.

Key table: `patient` — contains demographics, ICU stay info, and the
`apacheadmissiondx` column which holds the APACHE IV admission diagnosis
as a free-text string (e.g., "Sepsis, pulmonary", "Infarction, acute
myocardial (MI)", "CABG alone, coronary artery bypass grafting").

**Important eICU conventions:**
- The primary ICU stay identifier is `patientunitstayid`
- Patient identifiers: `uniquepid` (patient), `patienthealthsystemstayid`
  (hospital stay), `patientunitstayid` (ICU stay)
- `apacheadmissiondx` may be NULL for some patients

Map each patient's `apacheadmissiondx` into one of these clinically
meaningful diagnosis groups:

| Group | Description | Example Diagnoses |
|-------|-------------|-------------------|
| ACS | Acute coronary syndromes | Unstable angina, acute MI |
| ChestPainUnknown | Non-cardiac chest pain | Atypical, epigastric, musculoskeletal |
| CHF | Heart failure | Cardiomyopathy, CHF, cardiogenic shock |
| CVOther | Other cardiovascular | Endocarditis, pericarditis, vascular |
| CardiacArrest | Cardiac arrest/arrhythmias | Cardiac arrest, rhythm disturbances |
| CABG | Coronary bypass surgery | All CABG variants |
| ValveDz | Valve disease/surgery | Valve repair/replacement |
| PNA | Pneumonia | Bacterial, viral, aspiration, fungal |
| RespMedOther | Other respiratory | ARDS, PE, pneumothorax, tracheostomy |
| Asthma-Emphys | Obstructive lung disease | Asthma, emphysema/bronchitis |
| GIBleed | GI bleeding | Upper/lower GI bleed, variceal |
| GIObstruction | GI obstruction | Obstruction, lysis of adhesions |
| CVA | Cerebrovascular accident | Stroke, intracranial hemorrhage, SAH |
| Neuro | Other neurologic | Seizures, neoplasm, abscess |
| Coma | Coma | Change in consciousness, anoxic coma |
| Overdose | Drug overdose/toxicity | All overdose types, drug toxicity |
| Sepsis | Sepsis | Pulmonary, UTI, GI, cutaneous sepsis |
| ARF | Acute renal failure | Acute renal failure, obstruction |
| DKA | Diabetic emergencies | DKA, HHNC |
| Trauma | Trauma (all types) | All trauma combinations |
| Other | All other diagnoses | Everything not in above groups |

Patients with NULL `apacheadmissiondx` should be mapped to "Other".

Output a CSV file to `{output_path}` with these exact columns:
patientunitstayid, uniquepid, patienthealthsystemstayid, apachedxgroup, apacheadmissiondx

One row per ICU stay (all patients).
