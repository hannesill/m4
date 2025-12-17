# Adding Custom Datasets

M4 supports any PhysioNet dataset. This guide shows how to add your own.

## Quick Start: JSON Definition

Create a JSON file in `m4_data/datasets/`:

**Example: `m4_data/datasets/mimic-iv-ed.json`**
```json
{
  "name": "mimic-iv-ed",
  "description": "MIMIC-IV Emergency Department Module",
  "file_listing_url": "https://physionet.org/files/mimic-iv-ed/2.2/",
  "subdirectories_to_scan": ["ed"],
  "primary_verification_table": "ed_edstays",
  "requires_authentication": true,
  "bigquery_project_id": "physionet-data",
  "bigquery_dataset_ids": ["mimiciv_ed"],
  "modalities": ["TABULAR"]
}
```

Then initialize:
```bash
m4 init mimic-iv-ed --src /path/to/your/csv/files
```

## JSON Fields Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier (used in `m4 use <name>`) |
| `description` | Yes | Human-readable description |
| `file_listing_url` | No | PhysioNet URL for auto-download (demo datasets only) |
| `subdirectories_to_scan` | No | Subdirs containing CSV files (e.g., `["hosp", "icu"]`) |
| `primary_verification_table` | Yes | Table to verify initialization succeeded |
| `requires_authentication` | No | `true` if PhysioNet credentialing required |
| `bigquery_project_id` | No | GCP project for BigQuery access |
| `bigquery_dataset_ids` | No | BigQuery dataset IDs |
| `modalities` | No | Data types in this dataset (see below). Defaults to `["TABULAR"]` |

### Available Modalities

| Modality | Description | Available Tools |
|----------|-------------|-----------------|
| `TABULAR` | Structured tables (labs, demographics, vitals, etc.) | `get_database_schema`, `get_table_info`, `execute_query` |
| `NOTES` | Clinical notes and discharge summaries | `search_notes`, `get_note`, `list_patient_notes` |

Tools are filtered based on the dataset's declared modalities. If not specified, defaults to `["TABULAR"]`.

## Initialization Process

When you run `m4 init <dataset>`:

1. **Download** (if `file_listing_url` exists and files missing)
2. **Convert** CSV.gz files to Parquet format
3. **Create** DuckDB views over the Parquet files
4. **Verify** by querying `primary_verification_table`

## Directory Structure

M4 organizes data like this:

```
m4_data/
├── datasets/           # Custom JSON definitions
│   └── my-dataset.json
├── raw_files/          # Downloaded CSV.gz files
│   └── my-dataset/
│       └── *.csv.gz
├── parquet/            # Converted Parquet files
│   └── my-dataset/
│       └── *.parquet
└── databases/          # DuckDB databases
    └── my_dataset.duckdb
```

## Using Existing CSV Files

If you already have CSV files, point to them with `--src`:

```bash
m4 init my-dataset --src /path/to/csvs
```

M4 will:
1. Convert the CSVs to Parquet
2. Create DuckDB views
3. Set the dataset as active

## Credentialed Datasets

For datasets requiring PhysioNet credentials (most full datasets):

1. Get credentialed access on PhysioNet
2. Download manually using wget:
   ```bash
   wget -r -N -c -np --user YOUR_USERNAME --ask-password \
     https://physionet.org/files/dataset-name/version/ \
     -P m4_data/raw_files/dataset-name
   ```
3. Initialize:
   ```bash
   m4 init dataset-name
   ```

## Programmatic Registration

For more control, register datasets in Python:

```python
from m4.core.datasets import DatasetDefinition, DatasetRegistry, Modality

my_dataset = DatasetDefinition(
    name="my-custom-dataset",
    description="My custom clinical dataset",
    primary_verification_table="patients",
    modalities=frozenset({Modality.TABULAR}),
)

DatasetRegistry.register(my_dataset)
```

## Tips

- **Start with demo data:** Test your setup with `mimic-iv-demo` first
- **Check table names:** Use `get_database_schema` tool to see available tables
- **Verify initialization:** `m4 status` shows if Parquet and DuckDB are ready
- **Force reinitialize:** `m4 init <dataset> --force` recreates the database
