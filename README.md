# M4: Medical Data for LLMs

<p align="center">
  <img src="webapp/public/m4_logo_transparent.png" alt="M4 Logo" width="180"/>
</p>

<p align="center">
  <strong>Query clinical databases with natural language through Claude, Cursor, or any MCP client</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white"></a>
  <a href="https://modelcontextprotocol.io/"><img alt="MCP" src="https://img.shields.io/badge/MCP-Compatible-green?logo=ai&logoColor=white"></a>
  <a href="https://github.com/hannesill/m4/actions/workflows/tests.yaml"><img alt="Tests" src="https://github.com/hannesill/m4/actions/workflows/tests.yaml/badge.svg"></a>
</p>

M4 provides infrastructure for AI-assisted clinical research. It uses a modality-based architecture that enables the same natural language interface to query MIMIC-IV, eICU, and custom datasets without per-dataset engineering. Currently supports tabular data and clinical notes, with waveforms and imaging planned for future versions.


## Quickstart (3 steps)

### 1. Install uv

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Initialize M4

```bash
mkdir my-research && cd my-research
uv init && uv add m4-mcp
uv run m4 init mimic-iv-demo
```

This downloads the free MIMIC-IV demo dataset (~16MB) and sets up a local DuckDB database.

### 3. Connect your AI client

**Claude Desktop:**
```bash
uv run m4 config claude --quick
```

**Other clients (Cursor, LibreChat, etc.):**
```bash
uv run m4 config --quick
```

Copy the generated JSON into your client's MCP settings, restart, and start asking questions!

<details>
<summary>Different setup options</summary>

* If you don't want to use uv, you can just run pip install m4-mcp

* If you want to use Docker, look at <a href="docs/DEVELOPMENT.md">docs/DEVELOPMENT.md</a>
</details>


## Example Questions

Once connected, try asking:

**Tabular data (mimic-iv, eicu):**
- *"What tables are available in the database?"*
- *"Show me the race distribution in hospital admissions"*
- *"Find all ICU stays longer than 7 days"*
- *"What are the most common lab tests?"*

**Clinical notes (mimic-iv-note):**
- *"Search for notes mentioning diabetes"*
- *"List all notes for patient 10000032"*
- *"Get the full discharge summary for this patient"*


## Supported Datasets

| Dataset | Modality | Size | Access | Local | BigQuery |
|---------|----------|------|--------|-------|----------|
| **mimic-iv-demo** | Tabular | 100 patients | Free | Yes | No |
| **mimic-iv** | Tabular | 365k patients | [PhysioNet credentialed](https://physionet.org/content/mimiciv/) | Yes | Yes |
| **mimic-iv-note** | Notes | 331k notes | [PhysioNet credentialed](https://physionet.org/content/mimic-iv-note/) | Yes | Yes |
| **eicu** | Tabular | 200k+ patients | [PhysioNet credentialed](https://physionet.org/content/eicu-crd/) | Yes | Yes |

Switch datasets anytime:
```bash
m4 use mimic-iv     # Switch to full MIMIC-IV
m4 status           # See all available datasets
```

<details>
<summary><strong>Setting up MIMIC-IV or eICU (credentialed datasets)</strong></summary>

1. **Get PhysioNet credentials:** Complete the [credentialing process](https://physionet.org/settings/credentialing/) and sign the data use agreement for the dataset.

2. **Download the data:**
   ```bash
   # For MIMIC-IV
   wget -r -N -c -np --user YOUR_USERNAME --ask-password \
     https://physionet.org/files/mimiciv/3.1/ \
     -P m4_data/raw_files/mimic-iv

   # For eICU
   wget -r -N -c -np --user YOUR_USERNAME --ask-password \
     https://physionet.org/files/eicu-crd/2.0/ \
     -P m4_data/raw_files/eicu
   ```
   Put the downloaded data in a `m4_data` directory that ideally is located within the project directory. Name the directory for the dataset `mimic-iv`/`eicu`.

3. **Initialize:**
   ```bash
   m4 init mimic-iv   # or: m4 init eicu
   ```

This converts the CSV files to Parquet format and creates a local DuckDB database.
</details>


## Available Tools

M4 exposes these tools to your AI client. Tools are filtered based on the active dataset's modality.

**Dataset Management:**
| Tool | Description |
|------|-------------|
| `list_datasets` | List available datasets and their status |
| `set_dataset` | Switch the active dataset |

**Tabular Data Tools** (mimic-iv, mimic-iv-demo, eicu):
| Tool | Description |
|------|-------------|
| `get_database_schema` | List all available tables |
| `get_table_info` | Get column details and sample data |
| `execute_query` | Run SQL SELECT queries |

**Clinical Notes Tools** (mimic-iv-note):
| Tool | Description |
|------|-------------|
| `search_notes` | Full-text search with snippets |
| `get_note` | Retrieve a single note by ID |
| `list_patient_notes` | List notes for a patient (metadata only) |


## More Documentation

| Guide | Description |
|-------|-------------|
| [Tools Reference](docs/TOOLS.md) | Detailed tool documentation |
| [BigQuery Setup](docs/BIGQUERY.md) | Use Google Cloud for full datasets |
| [Custom Datasets](docs/CUSTOM_DATASETS.md) | Add your own PhysioNet datasets |
| [Development](docs/DEVELOPMENT.md) | Contributing, testing, architecture |
| [OAuth2 Authentication](docs/OAUTH2_AUTHENTICATION.md) | Enterprise security setup |

## Troubleshooting

**"Parquet not found" error:**
```bash
m4 init mimic-iv-demo --force
```

**MCP client won't connect:**
Check client logs (Claude Desktop: Help → View Logs) and ensure the config JSON is valid.

**Need to reconfigure:**
```bash
m4 config claude --quick   # Regenerate Claude Desktop config
m4 config --quick          # Regenerate generic config
```

## Citation

M4 builds on the M3 project. Please cite:

```bibtex
@article{attrach2025conversational,
  title={Conversational LLMs Simplify Secure Clinical Data Access, Understanding, and Analysis},
  author={Attrach, Rafi Al and Moreira, Pedro and Fani, Rajna and Umeton, Renato and Celi, Leo Anthony},
  journal={arXiv preprint arXiv:2507.01053},
  year={2025}
}
```

---

<p align="center">
  <a href="https://github.com/hannesill/m4/issues">Report an Issue</a> ·
  <a href="docs/DEVELOPMENT.md">Contribute</a>
</p>
