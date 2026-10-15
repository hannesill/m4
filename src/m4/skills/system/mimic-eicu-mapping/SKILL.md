---
name: mimic-eicu-mapping
description: Map MIMIC-IV identifiers, tables, time handling and concepts to eICU-CRD as M4 exposes it. Use when translating a MIMIC-IV query to eICU, validating a MIMIC-IV model on eICU, or running one analysis on both databases.
tier: community
category: system
kind: methodology
---

# MIMIC-IV to eICU Mapping

eICU-CRD 2.0 is multi-center (208 US hospitals, 2014-2015); MIMIC-IV is single-center. Apply these rules to every eICU query.

## Rules

1. **Check eICU is available.** It is credentialed. On the default DuckDB backend, the `eicu` entry of `m4 list-datasets --json` needs `"prepared": true`. On BigQuery (`m4 doctor --json` reports the backend and checks the credentials), it needs `bigquery_available`. Otherwise tell the user; never download it yourself.
2. **Prefix every table with `eicu_crd.`**: `eicu_crd.patient`, not `patient`. M4 exposes eICU only under this schema (`physionet-data.eicu_crd` on BigQuery).
3. **Time is an integer offset.** Each table has its own offset column, in minutes from this unit stay's admission (`labresultoffset`, `nursingchartoffset`, ...); negative means before. There are no dates; `hospitaldischargeyear` is the only year. MIMIC `intime - 6 h .. intime + 24 h` becomes `offset BETWEEN -360 AND 1440`.
4. **Age is text**, `'> 89'` for older patients: `CASE WHEN age = '> 89' THEN 91 ELSE TRY_CAST(age AS INTEGER) END` (`SAFE_CAST(age AS INT64)` on BigQuery). 91 matches MIMIC-IV's `anchor_age` for patients over 89.
5. **Clinical tables join on `patientunitstayid`.** One `patient` row is one unit stay and covers MIMIC's patients, admissions and icustays; it also holds the coarser keys: `patienthealthsystemstayid` (hospital stay), `uniquepid` (patient), and `hospitalid`, which joins `eicu_crd.hospital`.

## Identifiers

| MIMIC-IV | eICU |
|----------|------|
| `subject_id` | `uniquepid` |
| `hadm_id` | `patienthealthsystemstayid` |
| `stay_id` | `patientunitstayid` |
| ICU stay order within admission | `unitvisitnumber` |
| (single hospital) | `hospitalid` → `eicu_crd.hospital` |

## Tables

| MIMIC-IV | eICU | Offset; notes |
|----------|------|---------------|
| patients, admissions, icustays | patient | `hospitaladmitoffset`, `unitdischargeoffset`, `hospitaldischargeoffset`; `hospitaldischargestatus`, `unitdischargestatus` |
| chartevents (monitor vitals) | vitalperiodic, vitalaperiodic | `observationoffset`; `heartrate`, `respiration`, `sao2`, `systemicmean`; noninvasive BP in vitalaperiodic |
| chartevents (nurse-charted, GCS) | nursecharting | `nursingchartoffset`; text `nursingchartvalue`, keyed by `nursingchartcelltypevallabel` + `nursingchartcelltypevalname` |
| labevents | lab | `labresultoffset`; free-text `labname` (list with `SELECT labname, COUNT(*) FROM eicu_crd.lab GROUP BY 1`), numeric `labresult` |
| outputevents | intakeoutput | `intakeoutputoffset`; urine by `cellpath` |
| inputevents | infusiondrug | `infusionoffset` |
| prescriptions, emar | medication | `drugstartoffset`, `drugstopoffset` |
| microbiologyevents | microlab | `culturetakenoffset` |
| diagnoses_icd | diagnosis | `diagnosisoffset`; text `diagnosisstring`; `icd9code` coverage varies |
| (none) | admission diagnosis | `patient.apacheadmissiondx`, `apachepredvar.admitdiagnosis`, admissiondx |
| procedureevents (ventilation) | respiratorycare, treatment | `respcarestatusoffset`, `treatmentoffset` |
| (none) | apachepatientresult, apacheapsvar, apachepredvar | APACHE IV/IVa scores and predictions (one row per `apacheversion`); physiology inputs; predictors |

## Derived concepts

M4 builds `mimiciv_derived` for MIMIC-IV only. eicu-code's `pivoted_*` and eICU `icustay_detail` tables are not available in M4: compute concepts from the raw tables above.

## Example: highest heart rate in the first 24 h of the first ICU stay

MIMIC-IV:

```sql
SELECT ie.stay_id, MAX(ce.valuenum) AS hr_max
FROM mimiciv_icu.icustays ie
JOIN mimiciv_icu.chartevents ce
  ON ce.stay_id = ie.stay_id
 AND ce.itemid = 220045  -- heart rate
 AND ce.charttime BETWEEN ie.intime AND ie.intime + INTERVAL 1 DAY
WHERE ie.intime = (SELECT MIN(intime) FROM mimiciv_icu.icustays s WHERE s.hadm_id = ie.hadm_id)
GROUP BY ie.stay_id;
```

eICU:

```sql
SELECT vp.patientunitstayid, MAX(vp.heartrate) AS hr_max
FROM eicu_crd.vitalperiodic vp
JOIN eicu_crd.patient p ON p.patientunitstayid = vp.patientunitstayid
WHERE p.unitvisitnumber = 1
  AND vp.observationoffset BETWEEN 0 AND 1440
GROUP BY vp.patientunitstayid;
```

Hospital mortality: MIMIC `admissions.hospital_expire_flag`; eICU `hospitaldischargestatus = 'Expired'`, with missing status kept NULL rather than counted as survival.

## References

- Pollard TJ et al. "The eICU Collaborative Research Database, a freely available multi-center database for critical care research." Scientific Data. 2018;5:180178.
- Johnson AEW et al. "MIMIC-IV, a freely accessible electronic health record dataset." Scientific Data. 2023;10:1.
