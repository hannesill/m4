# Code Execution with the M4 Python API

The M4 Python API unlocks the full potential of LLM-assisted clinical research by giving you programmatic access to query results as native Python objects. Instead of parsing formatted text, you work directly with pandas DataFrames—enabling statistical analysis, visualization, and complex multi-step workflows.

## Why Code Execution?

MCP tools are great for exploratory questions: "What tables exist?" or "Show me patients over 80." But clinical research often requires more:

- **Iterative analysis**: Your first query reveals something interesting, and you need to dig deeper
- **Statistical rigor**: Computing confidence intervals, running survival analysis, or testing hypotheses
- **Large cohorts**: Working with thousands of patients without overwhelming your context window
- **Reproducibility**: Building analysis pipelines that can be re-run and shared

The Python API makes all of this natural. Same underlying tools, but with DataFrame outputs that integrate seamlessly with the scientific Python ecosystem.


## Quick Start

```python
from m4 import set_dataset, execute_query, get_schema, get_table_info

# 1. Select your dataset
set_dataset("mimic-iv")

# 2. Explore what's available
schema = get_schema()
print(schema['tables'])  # List of table names

# 3. Inspect a table
info = get_table_info("mimiciv_hosp.patients")
print(info['schema'])  # DataFrame: column names, types, descriptions
print(info['sample'])  # DataFrame: sample rows

# 4. Run queries
df = execute_query("SELECT * FROM mimiciv_hosp.patients LIMIT 1000")
print(df.head())
print(df.describe())
```


## API Reference

### Dataset Management

| Function | Returns | Description |
|----------|---------|-------------|
| `list_datasets()` | `list[str]` | Available dataset names |
| `set_dataset(name)` | `str` | Set active dataset (required before queries) |
| `get_active_dataset()` | `str` | Current dataset name |

```python
from m4 import list_datasets, set_dataset, get_active_dataset

print(list_datasets())  # ['mimic-iv', 'mimic-iv-note', 'eicu', ...]
set_dataset("mimic-iv")
print(get_active_dataset())  # 'mimic-iv'
```

### Tabular Data

| Function | Returns | Description |
|----------|---------|-------------|
| `get_schema()` | `dict` | Tables list and backend info |
| `get_table_info(table, show_sample=True)` | `dict` | Schema DataFrame and optional sample |
| `execute_query(sql)` | `DataFrame` | Query results |

```python
from m4 import execute_query, get_schema, get_table_info

# Schema exploration
schema = get_schema()
print(schema['backend_info'])  # 'DuckDB (local): /path/to/db'
print(schema['tables'])        # ['mimiciv_hosp.admissions', 'mimiciv_hosp.diagnoses_icd', ...]

# Table details
info = get_table_info("mimiciv_hosp.admissions")
print(info['schema'])  # DataFrame with column_name, data_type, description
print(info['sample'])  # DataFrame with sample rows

# Execute queries - returns pandas DataFrame
df = execute_query("""
    SELECT gender, COUNT(*) as count
    FROM mimiciv_hosp.patients
    GROUP BY gender
""")
print(df)
#   gender  count
# 0      M    185
# 1      F    165
```

> **Table naming convention:** Tables use canonical `schema.table` names (e.g., `mimiciv_hosp.patients`, `mimiciv_icu.icustays`) that work on both DuckDB and BigQuery backends. Use `get_schema()` to see all available tables.

### Clinical Notes

| Function | Returns | Description |
|----------|---------|-------------|
| `search_notes(query, note_type, limit, snippet_length)` | `dict` | Search results by note type |
| `get_note(note_id, max_length)` | `dict` | Full note text and metadata |
| `list_patient_notes(subject_id, note_type, limit)` | `dict` | Note metadata for a patient |

```python
from m4 import set_dataset, search_notes, get_note, list_patient_notes

set_dataset("mimic-iv-note")  # Dataset with NOTES modality

# Search across notes
results = search_notes("pneumonia", note_type="discharge", limit=10)
for note_type, df in results['results'].items():
    print(f"{note_type}: {len(df)} matches")
    print(df[['note_id', 'snippet']].head())

# Get full note
note = get_note("10000032_DS-1")
print(note['text'][:500])

# List patient's notes
notes = list_patient_notes(10000032)
for note_type, df in notes['notes'].items():
    print(f"{note_type}: {len(df)} notes")
```


## Error Handling

M4 uses typed exceptions for clear error recovery:

```
M4Error (base)
├── DatasetError      # Dataset not found or not configured
├── QueryError        # SQL error, table not found
└── ModalityError     # Tool incompatible with dataset
```

```python
from m4 import execute_query, set_dataset, DatasetError, QueryError, ModalityError

try:
    df = execute_query("SELECT * FROM mimiciv_hosp.patients")
except DatasetError:
    # No dataset selected
    set_dataset("mimic-iv")
    df = execute_query("SELECT * FROM mimiciv_hosp.patients")
except QueryError as e:
    # Bad SQL or missing table
    print(f"Query failed: {e}")
except ModalityError:
    # Tried notes function on tabular-only dataset
    set_dataset("mimic-iv-note")
```


## Real-World Example: Mortality Analysis

Here's how the Python API enables a complete analysis workflow:

```python
from m4 import set_dataset, execute_query
import pandas as pd

set_dataset("mimic-iv")

# Step 1: Get ICU stays with outcomes
icu_stays = execute_query("""
    SELECT
        i.stay_id,
        i.subject_id,
        i.los,
        a.hospital_expire_flag,
        p.gender,
        p.anchor_age as age
    FROM mimiciv_icu.icustays i
    JOIN mimiciv_hosp.admissions a ON i.hadm_id = a.hadm_id
    JOIN mimiciv_hosp.patients p ON i.subject_id = p.subject_id
""")

# Step 2: Analyze with pandas
print(f"Total ICU stays: {len(icu_stays)}")
print(f"Mortality rate: {icu_stays['hospital_expire_flag'].mean():.1%}")

# Step 3: Stratify by age group
icu_stays['age_group'] = pd.cut(
    icu_stays['age'],
    bins=[0, 50, 65, 80, 120],
    labels=['<50', '50-64', '65-79', '80+']
)

mortality_by_age = icu_stays.groupby('age_group')['hospital_expire_flag'].agg(['mean', 'count'])
print(mortality_by_age)

# Step 4: Statistical test
from scipy import stats
young = icu_stays[icu_stays['age'] < 65]['hospital_expire_flag']
old = icu_stays[icu_stays['age'] >= 65]['hospital_expire_flag']
stat, pval = stats.mannwhitneyu(young, old)
print(f"Age difference p-value: {pval:.4f}")
```

This workflow is natural in a code execution environment: the LLM writes and runs the code, iterating based on results until the analysis is complete.


## When to Use Code vs MCP Tools

| Use Case | Recommendation |
|----------|----------------|
| "What tables are in the database?" | MCP tool - simple exploration |
| "Count patients by gender" | Either - simple query |
| "Analyze mortality predictors with statistics" | **Python API** - multi-step analysis |
| "Build a cohort and compute survival curves" | **Python API** - complex workflow |
| "Search notes for 'sepsis'" | MCP tool - unless processing results |
| "Extract diagnoses from notes and correlate with labs" | **Python API** - cross-modal analysis |

The Python API shines when you need to:
- Chain multiple queries together
- Perform statistical computations
- Handle large result sets
- Build reproducible analysis pipelines


## Integration with Claude Code

Claude Code can execute Python directly, making the API immediately useful. See [this example session](M4_Code_Execution_Example.pdf) for a walkthrough.

When you ask Claude to analyze clinical data, it can:

1. Import the M4 API
2. Write analysis code
3. Execute it in the sandbox
4. Interpret results and iterate

Install the M4 skills to give Claude contextual knowledge about the API:

```bash
m4 skills --tools claude
```

See [Skills Guide](SKILLS.md) for more on how skills enhance Claude's capabilities.
