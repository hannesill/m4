# MCP Tools Reference

M4 exposes these tools to AI clients via the Model Context Protocol.

## Dataset Management

### `list_datasets`
List all available datasets and their status.

**Parameters:** None

**Example response:**
```
Available datasets:
- mimic-iv-demo (active) - MIMIC-IV Clinical Database Demo
- mimic-iv - MIMIC-IV Clinical Database
- eicu - eICU Collaborative Research Database
```

### `set_dataset`
Switch the active dataset.

**Parameters:**
- `dataset_name` (string, required): Name of the dataset to activate

**Example:**
```
set_dataset("mimic-iv")
```

---

## Schema Exploration

### `get_database_schema`
List all tables in the current dataset.

**Parameters:** None

**Returns:** Table names with row counts

### `get_table_info`
Get detailed information about a specific table.

**Parameters:**
- `table_name` (string, required): Name of the table
- `sample_rows` (int, optional): Number of sample rows to return (default: 5)

**Returns:** Column names, types, and sample data

---

## Query Execution

### `execute_query`
Execute a read-only SQL SELECT query.

**Parameters:**
- `query` (string, required): SQL SELECT statement
- `limit` (int, optional): Maximum rows to return (default: 100)

**Security:**
- Only SELECT statements allowed
- DROP, DELETE, INSERT, UPDATE blocked
- Query validation before execution

**Example:**
```sql
SELECT subject_id, gender, anchor_age
FROM hosp_patients
WHERE anchor_age > 65
LIMIT 10
```

---

## Clinical Data Tools

### `get_icu_stays`
Retrieve ICU admission data including length of stay.

**Parameters:**
- `patient_id` (int, optional): Filter by specific patient
- `limit` (int, optional): Maximum results (default: 10)

**Returns:** ICU stay records with admission time, discharge time, and duration

**Required capabilities:** `ICU_STAYS`

### `get_lab_results`
Query laboratory test results.

**Parameters:**
- `patient_id` (int, optional): Filter by specific patient
- `item_id` (int, optional): Filter by specific lab test
- `limit` (int, optional): Maximum results (default: 50)

**Returns:** Lab results with test names, values, units, and timestamps

**Required capabilities:** `LAB_RESULTS`

### `get_race_distribution`
Get patient demographics by race/ethnicity.

**Parameters:** None

**Returns:** Count and percentage breakdown by race category

**Required capabilities:** `DEMOGRAPHIC_STATS`

---

## Capability-Based Availability

Tools declare two types of requirements:

- **Modalities**: High-level data types (currently `TABULAR`, with `NOTES`, `IMAGING`, `WAVEFORM` planned for future versions)
- **Capabilities**: Specific operations like `ICU_STAYS`, `LAB_RESULTS`, etc.

Tools are automatically enabled or disabled based on the active dataset's capabilities:

| Tool | Required Capability | mimic-iv-demo | mimic-iv | eicu |
|------|---------------------|---------------|----------|------|
| `get_icu_stays` | `ICU_STAYS` | Yes | Yes | Yes |
| `get_lab_results` | `LAB_RESULTS` | Yes | Yes | Yes |
| `get_race_distribution` | `DEMOGRAPHIC_STATS` | Yes | Yes | Yes |
| `execute_query` | `COHORT_QUERY` | Yes | Yes | Yes |
| `get_database_schema` | `SCHEMA_INTROSPECTION` | Yes | Yes | Yes |

When a tool is unavailable for the current dataset, it returns a helpful error message explaining which capabilities are missing and suggests alternatives.

---

## Error Handling

Tools return structured error messages:

```
Error: Tool `get_icu_stays` is not available for dataset 'limited-dataset'.

Missing capabilities: ICU_STAYS

Tool requires:
   Modalities: TABULAR
   Capabilities: ICU_STAYS

Dataset 'limited-dataset' provides:
   Modalities: TABULAR
   Capabilities: COHORT_QUERY

Suggestions:
   - Use `list_datasets()` to see all available datasets
   - Use `set_dataset('dataset-name')` to switch datasets
```
