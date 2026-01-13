# M4: Infrastructure for AI-Assisted Clinical Research

<p align="center">
  <img src="webapp/public/m4_logo_transparent.png" alt="M4 Logo" width="180"/>
</p>

<p align="center">
  <strong>Give your AI agents clinical intelligence & access to MIMIC-IV, eICU, and more</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white"></a>
  <a href="https://modelcontextprotocol.io/"><img alt="MCP" src="https://img.shields.io/badge/MCP-Compatible-green?logo=ai&logoColor=white"></a>
  <a href="https://github.com/hannesill/m4/actions/workflows/tests.yaml"><img alt="Tests" src="https://github.com/hannesill/m4/actions/workflows/tests.yaml/badge.svg"></a>
</p>

M4 is infrastructure for AI-assisted clinical research. Initialize MIMIC-IV, eICU, or custom datasets as fast local databases (with optional BigQuery for cloud access). Your AI agents get specialized tools (MCP, Python API) and clinical knowledge (agent skills) to query and analyze them.

[Usage example – M4 MCP](https://claude.ai/share/93f26832-f298-4d1d-96e3-5608d7f0d7ad)

> M4 builds on the [M3](https://github.com/rafiattrach/m3) project. Please [cite](#citation) their work when using M4!


## Why M4?

Clinical research shouldn't require mastering database schemas. Whether you're screening a hypothesis, characterizing a cohort, or running a multi-step survival analysis—you should be able to describe what you want and get clinically meaningful results.

M4 makes this possible by giving AI agents deep clinical knowledge:

**Understand clinical semantics.** 
LLMs can write SQL, but have a harder time with (dataset-specific) clinical semantics. M4's comprehensive agent skills encode validated clinical concepts—so "find sepsis patients" produces clinically correct queries on any supported dataset.

**Work across modalities.** 
Clinical research with M4 spans structured data, clinical notes, and (soon) waveforms and imaging. M4 dynamically selects tools based on what each dataset contains—query labs in MIMIC-IV, search discharge summaries in MIMIC-IV-Note, all through the same interface.

**Go beyond chat.** 
Data exploration and simple research questions work great via MCP. But real research requires iteration: explore a cohort, compute statistics, visualize distributions, refine criteria. M4's Python API returns DataFrames that integrate with pandas, scipy, and matplotlib—turning your AI assistant into a research partner that can execute complete analysis workflows.

**Cross-dataset research.** 
You should be able to ask for multi-dataset queries or cross-dataset comparisons. M4 makes this easier than ever as the AI can switch between your initialized datasets on its own, allowing it to do cross-dataset tasks for you.


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
<summary>Different setup options</summary>

* If you don't want to use uv, you can just run pip install m4-infra

* If you want to use Docker, look at <a href="docs/DEVELOPMENT.md">docs/DEVELOPMENT.md</a>
</details>


## Code Execution

For complex analysis that goes beyond simple queries, M4 provides a Python API that returns Python data types instead of formatted strings (e.g. pd.DataFrame for SQL queries). This transforms M4 from a query tool into a complete clinical data analysis environment.

```python
from m4 import set_dataset, execute_query, get_schema

set_dataset("mimic-iv")

# Get schema as a dict
schema = get_schema()
print(schema['tables'])  # ['admissions', 'diagnoses_icd', ...]

# Query returns a pandas DataFrame
df = execute_query("""
    SELECT icd_code, COUNT(*) as n
    FROM hosp_diagnoses_icd
    GROUP BY icd_code
    ORDER BY n DESC
    LIMIT 10
""")

# Use full pandas power: filter, join, compute statistics
df[df['n'] > 100].plot(kind='bar')
```

The API uses the same tools as the MCP server, so behavior is consistent. But instead of parsing text, you get DataFrames you can immediately analyze, visualize, or feed into downstream pipelines.

**When to use code execution:**
- Multi-step analyses where each query informs the next
- Large result sets (thousands of rows) that shouldn't flood your context
- Statistical computations, survival analysis, cohort characterization
- Building reproducible analysis notebooks

See [Code Execution Guide](docs/CODE_EXECUTION.md) for the full API reference.


## Agent Skills

M4 ships with 17 skills that teach AI coding assistants clinical research patterns. Skills activate automatically when relevant—ask about "SOFA scores" or "sepsis cohorts" and Claude uses validated SQL from MIT-LCP repositories.

**Included skills:**
- **API**: `m4-api` for Python API usage
- **Severity Scores**: SOFA, APACHE III, SAPS-II, OASIS, LODS, SIRS
- **Sepsis**: Sepsis-3 cohort identification, suspected infection
- **Organ Failure**: KDIGO AKI staging
- **Measurements**: GCS calculation, baseline creatinine, vasopressor equivalents
- **Cohort Selection**: First ICU stay identification
- **Data Quality**: Table relationships, MIMIC-eICU mapping, research pitfalls

**Supported tools:** Claude Code, Cursor, Cline, Codex CLI, Gemini CLI, GitHub Copilot

```bash
m4 skills                        # Interactive tool selection
m4 skills --tools claude,cursor  # Install for specific tools
m4 skills --list                 # Show installed skills
```

See [Skills Guide](docs/SKILLS.md) for the full list and how to create custom skills.


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

These datasets are supported out of the box. However, it is possible to add any other custom dataset by following [these instructions](docs/CUSTOM_DATASETS.md).

Switch datasets anytime:
```bash
m4 use mimic-iv     # Switch to full MIMIC-IV
m4 status           # Show active dataset details
m4 status --all     # List all available datasets
```

<details>
<summary><strong>Setting up MIMIC-IV or eICU (credentialed datasets)</strong></summary>

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
   The `--cut-dirs=2 -nH` flags ensure CSV files land directly in `m4_data/raw_files/mimic-iv/` rather than a nested `physionet.org/files/...` structure.

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
| [Architecture](docs/ARCHITECTURE.md) | Design philosophy, system overview, clinical semantics |
| [Code Execution](docs/CODE_EXECUTION.md) | Python API for programmatic access |
| [Skills](docs/SKILLS.md) | 17 clinical research skills and custom skill creation |
| [Tools Reference](docs/TOOLS.md) | MCP tool documentation |
| [BigQuery Setup](docs/BIGQUERY.md) | Google Cloud for full datasets |
| [Custom Datasets](docs/CUSTOM_DATASETS.md) | Add your own PhysioNet datasets |
| [Development](docs/DEVELOPMENT.md) | Contributing, testing, code style |
| [OAuth2 Authentication](docs/OAUTH2_AUTHENTICATION.md) | Enterprise security setup |

## Roadmap

M4 is infrastructure for AI-assisted clinical research. Current priorities:

- **Clinical Semantics**
  - More concept mappings (comorbidity indices, medication classes)
  - Semantic search over clinical notes (beyond keyword matching)
  - More agent skills that provide meaningful clinical knowledge

- **New Modalities**
  - Waveforms (ECG, arterial blood pressure)
  - Imaging (chest X-rays)

- **Clinical Research Agents**
  - Skills and guardrails that enforce scientific integrity and best practices (documentation, etc.)
  - Query logging and session export
  - Result fingerprints for audit trails

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
