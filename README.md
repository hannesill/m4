# M4: Infrastructure for AI-Assisted Clinical Research

<p align="center">
  <img src="webapp/public/m4_logo_transparent.png" alt="M4 Logo" width="180"/>
</p>

<p align="center">
  <strong>Query clinical databases with AI — grounded in clinician-reviewed knowledge</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white"></a>
  <a href="https://modelcontextprotocol.io/"><img alt="MCP" src="https://img.shields.io/badge/MCP-Compatible-green?logo=ai&logoColor=white"></a>
  <a href="https://github.com/hannesill/m4/actions/workflows/tests.yaml"><img alt="Tests" src="https://github.com/hannesill/m4/actions/workflows/tests.yaml/badge.svg"></a>
  <a href="docs/index.md"><img alt="Docs" src="https://img.shields.io/badge/Docs-Documentation-blue"></a>
</p>

M4 connects your AI assistant to clinical databases like MIMIC-IV and eICU. Ask questions in plain English, automate research tasks through a Python API, and ground your agent in clinician-reviewed definitions and best practices — all from Claude, Cursor, or any MCP-compatible tool.

[Usage example – M4 MCP](https://claude.ai/share/93f26832-f298-4d1d-96e3-5608d7f0d7ad) | [Usage example – Code Execution](docs/assets/M4_Code_Execution_Example.pdf)

> M4 builds on the [M3](https://github.com/rafiattrach/m3) project. Please [cite](#citation) their work when using M4!

> **Never used a terminal?** The [Getting Started guide](docs/getting-started/index.md) explains everything from opening a terminal to your first query.


## Why M4?

- **Ask questions in plain English.** Query MIMIC-IV, eICU, and other clinical databases directly from Claude, Cursor, or any MCP-compatible AI client — no SQL required.
- **Automate research tasks.** Let your AI agent build cohorts, compute severity scores, run survival analyses, and generate publication-ready tables through M4's Python API.
- **Ground your agent in clinical knowledge.** A library of agent skills provides validated, clinician-reviewed definitions, best practices, and domain knowledge — so your agent applies proven methods instead of improvising.
- **Work across datasets.** Switch seamlessly between databases for multi-center studies and external validation — or add your own datasets.


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
uv init && uv add m4-infra
source .venv/bin/activate  # Windows: .venv\Scripts\activate
m4 init mimic-iv-demo
```

This downloads the free MIMIC-IV demo dataset (~16MB) and sets up a local DuckDB database.

### 3. Connect your AI client

**Claude Desktop:**
```bash
m4 config claude --quick
```

**Other clients (Cursor, LibreChat, etc.):**
```bash
m4 config --quick
```

Copy the generated JSON into your client's MCP settings, restart, and start asking questions!

<details>
<summary>Alternative setup options</summary>

* If you don't want to use uv, you can run `pip install m4-infra`
* If you want to use Docker, see the [Development Guide](docs/development/contributing.md)
</details>


## Code Execution

For complex analysis that goes beyond simple queries, M4 provides a Python API that returns native Python types (DataFrames) instead of formatted strings:

```python
from m4 import set_dataset, execute_query, get_schema

set_dataset("mimic-iv")

schema = get_schema()
print(schema['tables'])  # ['mimiciv_hosp.admissions', 'mimiciv_hosp.diagnoses_icd', ...]

df = execute_query("""
    SELECT icd_code, COUNT(*) as n
    FROM mimiciv_hosp.diagnoses_icd
    GROUP BY icd_code ORDER BY n DESC LIMIT 10
""")

df[df['n'] > 100].plot(kind='bar')
```

Use code execution for multi-step analyses, statistical computations, survival analysis, large result sets, and reproducible notebooks. See the [Code Execution Guide](docs/guides/code-execution.md) for the full API reference.


## Agent Skills

M4 ships with skills that teach AI assistants clinical research patterns. Skills activate automatically when relevant — ask about "SOFA scores" or "sepsis cohorts" and the AI uses validated SQL from MIT-LCP repositories.

**Clinical skills:** SOFA, APACHE III, SAPS-II, OASIS, LODS, SIRS, Sepsis-3, KDIGO AKI, GCS, vasopressor equivalents, baseline creatinine, first ICU stay, research pitfalls

**System skills:** Python API usage, MIMIC-IV table relationships, MIMIC-eICU mapping, skill creation guide

**Supported tools:** Claude Code, Cursor, Cline, Codex CLI, Gemini CLI, GitHub Copilot

```bash
m4 skills                                    # Interactive tool and skill selection
m4 skills --tools claude,cursor              # Install all skills for specific tools
m4 skills --tools claude --tier validated     # Only validated skills
m4 skills --list                             # Show installed skills with metadata
```

See the [Skills Guide](docs/guides/skills.md) for the full list and how to create custom skills.


## Example Questions

**Tabular data (mimic-iv, eicu):**
- *"What tables are available in the database?"*
- *"Show me the race distribution in hospital admissions"*
- *"Find all ICU stays longer than 7 days"*

**Derived concept tables (mimic-iv, after `m4 init-derived`):**
- *"What are the average SOFA scores for patients with sepsis?"*
- *"Show KDIGO AKI staging distribution across ICU stays"*

**Clinical notes (mimic-iv-note):**
- *"Search for notes mentioning diabetes"*
- *"Get the full discharge summary for this patient"*


## Supported Datasets

| Dataset | Modality | Patients | Access | Local | BigQuery | Derived Tables |
|---------|----------|----------|--------|-------|----------|----------------|
| **mimic-iv-demo** | Tabular | 100 | Free | Yes | No | No |
| **mimic-iv** | Tabular | 365k | [PhysioNet credentialed](https://physionet.org/content/mimiciv/) | Yes | Yes | Yes (63 tables) |
| **mimic-iv-note** | Notes | 331k notes | [PhysioNet credentialed](https://physionet.org/content/mimic-iv-note/) | Yes | Yes | No |
| **eicu** | Tabular | 200k+ | [PhysioNet credentialed](https://physionet.org/content/eicu-crd/) | Yes | Yes | No |

Custom datasets can be added via JSON definition. See the [Datasets Guide](docs/getting-started/datasets.md) for full setup instructions including credentialed datasets.

```bash
m4 use mimic-iv         # Switch to full MIMIC-IV
m4 backend bigquery     # Switch to BigQuery (or duckdb)
m4 status               # Show active dataset and backend
m4 status --all         # List all available datasets
```

**Derived concept tables** (MIMIC-IV only): ~63 pre-computed tables (SOFA, sepsis3, KDIGO, etc.) from [mimic-code](https://github.com/MIT-LCP/mimic-code). BigQuery users already have these via `physionet-data.mimiciv_derived`.

```bash
m4 init-derived mimic-iv         # Materialize derived tables
m4 init-derived mimic-iv --list  # Preview available tables
```

<details>
<summary><strong>Setting up credentialed datasets (MIMIC-IV, eICU)</strong></summary>

1. **Get PhysioNet credentials:** Complete the [credentialing process](https://physionet.org/settings/credentialing/) and sign the data use agreement for the dataset.

2. **Download the data:**
   ```bash
   # For MIMIC-IV
   wget -r -N -c -np --cut-dirs=2 -nH --user YOUR_USERNAME --ask-password \
     https://physionet.org/files/mimiciv/3.1/ \
     -P m4_data/raw_files/mimic-iv

   # For eICU
   wget -r -N -c -np --cut-dirs=2 -nH --user YOUR_USERNAME --ask-password \
     https://physionet.org/files/eicu-crd/2.0/ \
     -P m4_data/raw_files/eicu
   ```

3. **Initialize:**
   ```bash
   m4 init mimic-iv   # or: m4 init eicu
   ```

This converts the CSV files to Parquet format and creates a local DuckDB database.
</details>


## Available Tools

M4 exposes these MCP tools to your AI client, filtered by the active dataset's modality:

| Tool | Description | Datasets |
|------|-------------|----------|
| `list_datasets` | List available datasets and their status | All |
| `set_dataset` | Switch the active dataset | All |
| `get_database_schema` | List all available tables | Tabular |
| `get_table_info` | Get column details and sample data | Tabular |
| `execute_query` | Run SQL SELECT queries | Tabular |
| `search_notes` | Full-text search with snippets | Notes |
| `get_note` | Retrieve a single note by ID | Notes |
| `list_patient_notes` | List notes for a patient (metadata only) | Notes |

See the [Tools Reference](docs/reference/tools.md) for full documentation including derived table categories.


## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started/index.md) | Install M4 and run your first query (zero CLI experience needed) |
| [Datasets](docs/getting-started/datasets.md) | Choose and set up datasets (demo, MIMIC-IV, eICU, BigQuery) |
| [First Analysis](docs/getting-started/first-analysis.md) | End-to-end tutorial from setup to clinical insights |
| [Code Execution](docs/guides/code-execution.md) | Python API for programmatic access |
| [Skills](docs/guides/skills.md) | Clinical and system skills (SOFA, sepsis, KDIGO, etc.) |
| [M4 Apps](docs/guides/apps.md) | Interactive UIs for clinical research tasks |
| [BigQuery](docs/guides/bigquery.md) | Cloud access to full datasets |
| [Custom Datasets](docs/guides/custom-datasets.md) | Add your own datasets |
| [Tools Reference](docs/reference/tools.md) | MCP tool documentation and derived tables |
| [Architecture](docs/reference/architecture.md) | Design philosophy and system overview |
| [OAuth2](docs/reference/oauth2.md) | Enterprise authentication setup |
| [Development](docs/development/contributing.md) | Contributing, testing, code style |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |


## Troubleshooting

**`m4` command opens GNU M4 instead of the CLI:**
Make sure your virtual environment is activated (`source .venv/bin/activate`). Alternatively, use `uv run m4 [command]` to run within the project environment without activating it.

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

See the [full troubleshooting guide](docs/troubleshooting.md) for Windows-specific issues, BigQuery errors, and more.


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
  <a href="./docs/development/contributing.md">Contribute</a> ·
  <a href="./docs/index.md">Documentation</a>
</p>
