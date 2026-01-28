# MCP Tools Reference

M4 exposes these tools to AI clients via the Model Context Protocol. Tools are filtered based on the active dataset's modality.

## Dataset Management

### `list_datasets`
List all available datasets and their status.

**Parameters:** None

**Example response:**
```
Available datasets:
- mimic-iv-demo (active) - MIMIC-IV Clinical Database Demo [TABULAR]
- mimic-iv - MIMIC-IV Clinical Database [TABULAR]
- mimic-iv-note - MIMIC-IV Clinical Notes [NOTES]
- eicu - eICU Collaborative Research Database [TABULAR]
```

### `set_dataset`
Switch the active dataset.

**Parameters:**
- `dataset_name` (string, required): Name of the dataset to activate

**Example:**
```
set_dataset("mimic-iv-note")
```

---

## Tabular Data Tools

These tools are available for datasets with the `TABULAR` modality (mimic-iv, mimic-iv-demo, eicu).

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
FROM mimiciv_hosp.patients
WHERE anchor_age > 65
LIMIT 10
```

---

## Clinical Notes Tools

These tools are available for datasets with the `NOTES` modality (mimic-iv-note). They are designed to prevent context overflow by returning snippets and metadata instead of full text by default.

### `search_notes`
Full-text search across clinical notes. Returns snippets around matches.

**Parameters:**
- `query` (string, required): Search term
- `note_type` (string, optional): Filter by type - `"discharge"`, `"radiology"`, or `"all"` (default: `"all"`)
- `limit` (int, optional): Maximum results (default: 5)
- `snippet_length` (int, optional): Characters around match (default: 300)

**Returns:** Note IDs, subject IDs, and text snippets around matches

**Example:**
```
search_notes("diabetes", note_type="discharge", limit=10)
```

**Tip:** Use `get_note(note_id)` to retrieve the full text of a specific note.

### `get_note`
Retrieve the full text of a single clinical note by ID.

**Parameters:**
- `note_id` (string, required): The note identifier (e.g., `"10000032_DS-1"`)
- `max_length` (int, optional): Truncate output to this length

**Returns:** Full note text (or truncated if `max_length` specified)

**Warning:** Clinical notes can be very long (10,000+ characters). Consider using `search_notes()` first to find relevant notes, then retrieve specific ones.

**Example:**
```
get_note("10000032_DS-1")
get_note("10000032_DS-1", max_length=5000)  # Truncate to 5000 chars
```

### `list_patient_notes`
List available notes for a patient. Returns metadata only (IDs, types, lengths) - not full text.

**Parameters:**
- `subject_id` (int, required): Patient identifier
- `note_type` (string, optional): Filter by type - `"discharge"`, `"radiology"`, or `"all"` (default: `"all"`)
- `limit` (int, optional): Maximum results (default: 20)

**Returns:** Note IDs, types, lengths, and 100-character previews

**Example:**
```
list_patient_notes(10000032)
list_patient_notes(10000032, note_type="discharge")
```

**Tip:** Use this to discover what notes exist before retrieving them with `get_note()`.

---

## Modality-Based Tool Availability

Tools declare required modalities. Only datasets with matching modalities expose the tool:

| Tool | Required Modality | mimic-iv-demo | mimic-iv | mimic-iv-note | eicu |
|------|-------------------|---------------|----------|---------------|------|
| `get_database_schema` | TABULAR | Yes | Yes | No | Yes |
| `get_table_info` | TABULAR | Yes | Yes | No | Yes |
| `execute_query` | TABULAR | Yes | Yes | No | Yes |
| `search_notes` | NOTES | No | No | Yes | No |
| `get_note` | NOTES | No | No | Yes | No |
| `list_patient_notes` | NOTES | No | No | Yes | No |
| `list_datasets` | (always) | Yes | Yes | Yes | Yes |
| `set_dataset` | (always) | Yes | Yes | Yes | Yes |

---

## Working with Related Datasets

MIMIC-IV and MIMIC-IV-Note are separate datasets that can be linked via `subject_id`:

```
# 1. Find patients of interest in MIMIC-IV (tabular)
set_dataset("mimic-iv")
execute_query("SELECT subject_id FROM mimiciv_hosp.patients WHERE anchor_age > 80 LIMIT 5")

# 2. Switch to notes and explore their clinical narratives
set_dataset("mimic-iv-note")
list_patient_notes(10000032)
search_notes("heart failure", note_type="discharge")
get_note("10000032_DS-1")
```

---

## Error Handling

When a tool is unavailable for the current dataset, it returns a helpful error:

```
Error: Tool `search_notes` is not available for dataset 'mimic-iv'.

This tool requires the NOTES modality, but 'mimic-iv' only has: TABULAR

Suggestions:
   - Use `list_datasets()` to see all available datasets
   - Use `set_dataset('mimic-iv-note')` to switch to a notes dataset
```

---

## Note Types

Clinical notes in MIMIC-IV-Note come in two types:

| Type | Description | Typical Length |
|------|-------------|----------------|
| `discharge` | Discharge summaries - comprehensive narratives of hospital stays | 5,000-15,000 chars |
| `radiology` | Radiology reports - findings from imaging studies | 500-2,000 chars |

Use the `note_type` parameter to filter searches and listings.

---

## Python API Alternative

For complex analysis beyond simple queries, M4 provides a Python API that returns native types (DataFrames) instead of formatted strings. The API uses the same underlying tools but is designed for:

- Multi-step analyses where each query informs the next
- Statistical computations, survival analysis, cohort characterization
- Large result sets that shouldn't flood your context window
- Building reproducible analysis notebooks

```python
from m4 import set_dataset, execute_query

set_dataset("mimic-iv")
df = execute_query("SELECT * FROM mimiciv_hosp.patients")  # Returns pandas DataFrame
```

See [Code Execution Guide](CODE_EXECUTION.md) for the full API reference.
