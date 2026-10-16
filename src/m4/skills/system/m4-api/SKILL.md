---
name: m4-api
description: Query M4 clinical datasets (MIMIC-IV, MIMIC-IV-Note, MIMIC-IV-ED, eICU, MIMIC-III, and demos) from Python with `import m4`: find tables, run SQL into pandas, search clinical notes, handle M4's errors. Use before writing Python or SQL against M4 data.
tier: community
category: system
kind: integration
---

# M4 Python API

Every call names its dataset; M4 keeps no active dataset.

## Every query

1. Check which datasets are ready: `m4 list-datasets --json` (`"prepared": true`) or `m4 status --all`.
   `list_datasets()` returns every dataset M4 knows, downloaded or not. Adding data
   (`m4 init`, `m4 download`) needs the user's data access, so ask them first.
2. Find the tables and columns, then query with schema-qualified names:

```python
from m4 import M4Client

db = M4Client(dataset="mimic-iv-demo")
db.schema()["tables"]                           # ["mimiciv_hosp.admissions", ...]
db.table_info("mimiciv_icu.icustays")["schema"] # columns (name, type); ["sample"] holds rows
df = db.query("""
    SELECT first_careunit, COUNT(*) AS stays
    FROM mimiciv_icu.icustays
    GROUP BY first_careunit
    ORDER BY stays DESC
""")                                             # pandas DataFrame
```

`execute_query(sql, dataset=...)`, `get_schema(dataset=...)`, and
`get_table_info(table, dataset=...)` do the same without a client. From the shell:
`m4 query --dataset mimic-iv-demo --sql "SELECT ..."`.

A query returns every row it selects: aggregate in SQL and keep row-level results in
DataFrames, not in the conversation.

## Datasets

| Dataset | Schemas | Access |
|---|---|---|
| `mimic-iv-demo` | `mimiciv_hosp`, `mimiciv_icu` | open, 100 patients |
| `mimic-iv` | `mimiciv_hosp`, `mimiciv_icu`; `mimiciv_derived` after `m4 init-derived` | credentialed |
| `mimic-iv-note` | `mimiciv_note`, for the notes functions only | credentialed |
| `mimic-iv-ed-demo` | `mimiciv_ed` | open, the MIMIC-IV demo's 100 patients |
| `mimic-iv-ed` | `mimiciv_ed` | credentialed |
| `eicu-demo` | `eicu_crd`, as in `eicu` | open, over 2,500 unit stays |
| `eicu` | `eicu_crd` (`eicu_crd.patient`, never bare `patient`) | credentialed |
| `mimic-iii` | `mimiciii_clinical` | credentialed |

The MIMIC-IV demo has no `mimiciv_derived`; compute concepts there from the clinical skills' SQL.
Table names are the same on both backends. Write DuckDB SQL unless `m4 doctor --json` reports
the `bigquery` backend.

## Clinical notes

```python
notes = M4Client(dataset="mimic-iv-note")
hits = notes.search_notes("septic shock", note_type="discharge", limit=5)  # discharge, radiology, all
notes.list_patient_notes(subject_id, note_type="all", limit=20)
notes.get_note(note_id, max_length=4000)
```

## Errors

All derive from `m4.M4Error`. `m4` exports `DatasetError`, `QueryError`, and `ModalityError`;
the others are in `m4.core.exceptions`.

| Error | Usual cause | Next step |
|---|---|---|
| `ConnectionError` | "Database file not found": the dataset is not downloaded; or the database is locked by another process | Ask the user to add the dataset; retry when the other process ends |
| `DatasetError` | Unknown dataset name, or the removed `set_dataset()`/`get_active_dataset()` | Pass `dataset=` |
| `TableNotFoundError` | `table_info` on a table that does not exist | `schema()` |
| `QueryError` | SQL error, or a missing table or schema in the query | The message names the table or position |
| `SecurityError` | A statement other than `SELECT` | Queries are read-only |
| `ModalityError` | A notes function on a tabular dataset, or the reverse | Notes are in `mimic-iv-note` |

To show results to the researcher, use the `vitrine-api` skill.
