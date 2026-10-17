# Adding Custom Datasets

M4 works with your own data, and with PhysioNet datasets it does not ship.

## Quick Start: A Folder of Your Own Files

Put the tables in one folder as `.csv.gz` files, one file per table
(`gzip -k *.csv` compresses plain CSV files and keeps them). Then:

```bash
m4 define-dataset my-export --src /path/to/export --title "My ICU export"
m4 init my-export --src /path/to/export
```

`m4 define-dataset` saves the definition as `datasets/my-export.json` in the M4
data directory; `m4 init` converts the files and makes the tables. With
`--dry-run` it shows the tables without saving anything, and with `--json` it
prints them for scripts.

How the folder becomes tables:

- Files directly in the folder go into a schema named after the dataset:
  `admissions.csv.gz` becomes `my_export_data.admissions`. (A schema cannot
  share the name of the dataset's database, `my_export`.)
- Each subfolder that holds files becomes a schema named after it:
  `Lab Results/chemistry.csv.gz` becomes `lab_results.chemistry`.
- A table is named after its file, in lower case, so file names must be
  letters, digits and underscores. Files more than one folder deep, and two
  files that would make the same table, are refused.

Running `m4 define-dataset` again with the same name replaces the definition
it wrote, so a corrected folder needs only another run. A definition you wrote
by hand is replaced only with `--force`.

## Writing a Definition by Hand

For a PhysioNet dataset M4 does not ship, or to choose the schema names
yourself, create a JSON file in the M4 data directory under `datasets/`. By
default this is `m4_data/datasets/`; if `M4_DATA_DIR` is set, it must point
directly at the M4 data directory.

**Example: `m4_data/datasets/my-icu-extract.json`**

An extract from your own hospital's data warehouse, as CSV.gz files in a
`core/` and a `labs/` folder:

```json
{
  "name": "my-icu-extract",
  "title": "My ICU extract",
  "description": "Adult ICU extract from our data warehouse",
  "summary": "Admissions, vital signs and labs of adult ICU stays at one hospital.",
  "version": "2024-06",
  "subdirectories_to_scan": ["core", "labs"],
  "primary_verification_table": "myicu_core.admissions",
  "modalities": ["TABULAR"],
  "schema_mapping": {"core": "myicu_core", "labs": "myicu_labs"}
}
```

Then initialize:
```bash
m4 init my-icu-extract --src /path/to/your/csv/files
```

## JSON Fields Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier passed as `--dataset <name>` or `dataset="<name>"`. A file that uses the name of a built-in dataset (`mimic-iv-demo`, `mimic-iv`, `mimic-iv-note`, `mimic-iv-ed-demo`, `mimic-iv-ed`, `eicu-demo`, `eicu`, `mimic-iii`) is ignored with a warning |
| `description` | Yes | Human-readable description |
| `title` | No | Short display name shown by `m4 list-datasets`. Defaults to `name` |
| `summary` | No | One or two sentences on what the dataset holds, shown by `m4 list-datasets` |
| `version` | No | Version of the data, such as the PhysioNet version in `file_listing_url` |
| `download_size_gb` | No | Approximate size in GB of the raw CSV.gz files, shown by `m4 list-datasets` |
| `defined_from` | No | Set by `m4 define-dataset` to the folder it read. A file with it is replaced by the next `m4 define-dataset` of that name |
| `file_listing_url` | No | PhysioNet URL for auto-download (demo datasets only) |
| `subdirectories_to_scan` | No | Subdirs containing CSV files (e.g., `["hosp", "icu"]`) |
| `primary_verification_table` | Yes | Table to verify initialization succeeded |
| `requires_authentication` | No | `true` if PhysioNet credentialing required |
| `bigquery_project_id` | No | GCP project for BigQuery access |
| `bigquery_dataset_ids` | No | BigQuery dataset IDs |
| `modalities` | No | Data types in this dataset (see below). Defaults to `["TABULAR"]` |
| `schema_mapping` | No | Maps filesystem subdirectories to canonical schema names (see below) |
| `bigquery_schema_mapping` | No | Maps canonical schema names to BigQuery dataset IDs (see below) |

### Available Modalities

| Modality | Description | Available Tools |
|----------|-------------|-----------------|
| `TABULAR` | Structured tables (labs, demographics, vitals, etc.) | `get_database_schema`, `get_table_info`, `execute_query` |
| `NOTES` | Clinical notes and discharge summaries | `search_notes`, `get_note`, `list_patient_notes` |

Tools are filtered based on the dataset's declared modalities. If not specified, defaults to `["TABULAR"]`.

### Schema Mapping (Canonical Table Names)

M4 uses canonical `schema.table` names (e.g., `mimiciv_hosp.patients`) that work identically on both DuckDB and BigQuery backends. The `schema_mapping` and `bigquery_schema_mapping` fields control how these canonical names are constructed.

**`schema_mapping`** maps filesystem subdirectories to canonical schema names. When DuckDB creates views, files from each subdirectory are placed into the corresponding schema:

```json
{
  "schema_mapping": {
    "hosp": "mimiciv_hosp",
    "icu": "mimiciv_icu"
  }
}
```

With this mapping, a file at `hosp/patients.csv.gz` becomes queryable as `mimiciv_hosp.patients`.

A schema must not have the name DuckDB gives the dataset's database: its file
name up to the first dot, such as `my_dataset` for `my-dataset`. A query of
`my_dataset.patients` would then be ambiguous and fail.

For datasets where all files are in the root directory (no subdirectories), use an empty string key:

```json
{
  "schema_mapping": {
    "": "eicu_crd"
  }
}
```

**`bigquery_schema_mapping`** maps canonical schema names to BigQuery dataset IDs. This allows the BigQuery backend to translate canonical names to the actual GCP dataset names:

```json
{
  "bigquery_schema_mapping": {
    "mimiciv_hosp": "mimiciv_hosp",
    "mimiciv_icu": "mimiciv_icu"
  }
}
```

With this, a query for `mimiciv_hosp.patients` is rewritten to `physionet-data.mimiciv_hosp.patients` on BigQuery.

Custom datasets without `schema_mapping` still work — tables will be created with flat names in the `main` schema (backward-compatible behavior).

## Initialization Process

When you run `m4 init <dataset>`:

1. **Download** (if `file_listing_url` exists and files missing)
2. **Convert** CSV.gz files to Parquet format
3. **Create** DuckDB views over the Parquet files
4. **Verify** by querying `primary_verification_table`

## Directory Structure

M4 organizes data like this by default:

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

When `M4_DATA_DIR` is set, the same structure lives under that exact directory
instead of `./m4_data`.

## Using Existing CSV Files

If you already have the files of a defined dataset, point to them with `--src`:

```bash
m4 init my-dataset --src /path/to/csvs
```

M4 converts only `.csv.gz` files; compress plain `.csv` files first.

## Credentialed Datasets

M4 sends a PhysioNet login only to addresses that start with
`https://physionet.org/`. A credentialed dataset with any other
`file_listing_url` cannot be downloaded by M4, and M4 prints no `wget` command
for it, since that command asks for the PhysioNet password; download it
yourself and use `m4 init <dataset> --src`.

For datasets requiring PhysioNet credentials (most full datasets):

1. Get credentialed access on PhysioNet
2. Download manually using wget:
   ```bash
   wget -r -N -c -np --cut-dirs=3 -nH --user YOUR_USERNAME --ask-password \
     https://physionet.org/files/dataset-name/version/ \
     -P m4_data/raw_files/dataset-name
   ```
   Set `--cut-dirs` to the number of path components in the listing URL
   (`files/dataset-name/version` is 3) so files land in the top-level raw
   layout expected by `m4 init`.
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
