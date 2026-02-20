# M4: Infrastructure for AI-Assisted Clinical Research

<p align="center">
  <img src="assets/m4_logo_transparent.png" alt="M4 Logo" width="180"/>
</p>

<p align="center">
  <strong>Give your AI agents clinical intelligence & access to MIMIC-IV, eICU, and more</strong>
</p>

---

## What is M4?

M4 is infrastructure for AI-assisted clinical research. It gives AI agents specialized tools and clinical knowledge to query and analyze electronic health record (EHR) datasets like MIMIC-IV and eICU.

Initialize datasets as fast local databases, connect your AI client, and start asking clinical questions in natural language.

## Who is M4 for?

<div class="grid cards" markdown>

-   **Clinicians & Researchers**

    ---

    Ask clinical questions in plain English. No SQL or programming required.

    [:octicons-arrow-right-24: Getting Started](getting-started/index.md)

-   **Data Scientists & Developers**

    ---

    Use the Python API for multi-step analyses with pandas DataFrames.

    [:octicons-arrow-right-24: Code Execution](guides/code-execution.md)

-   **Research Teams**

    ---

    Scale to BigQuery for cloud access to full datasets with your team.

    [:octicons-arrow-right-24: BigQuery Setup](guides/bigquery.md)

</div>

## What makes M4 different?

- **Understands clinical semantics.** M4's agent skills encode validated clinical concepts from MIT-LCP repositories — "find sepsis patients" produces clinically correct queries, not just syntactically valid SQL.
- **Works across modalities.** Query labs in MIMIC-IV, search discharge summaries in MIMIC-IV-Note, all through the same interface. M4 dynamically selects tools based on what each dataset contains.
- **Goes beyond chat.** The Python API returns DataFrames that integrate with pandas, scipy, and matplotlib — turning your AI assistant into a research partner that executes complete analysis workflows.
- **Enables cross-dataset research.** Switch between datasets seamlessly. The AI handles MIMIC-IV and eICU differences so you can focus on your research question.

## Quick links

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started/index.md) | Install M4 and run your first query (zero experience needed) |
| [Datasets](getting-started/datasets.md) | Choose and set up the right dataset for your research |
| [First Analysis](getting-started/first-analysis.md) | End-to-end tutorial from setup to clinical insights |
| [Code Execution](guides/code-execution.md) | Python API for programmatic access |
| [Skills](guides/skills.md) | Clinical and system skills for AI-assisted research |
| [MCP Tools](reference/tools.md) | Tool documentation and derived table reference |
| [BigQuery](guides/bigquery.md) | Cloud access to full datasets |
| [Architecture](reference/architecture.md) | Design philosophy and system overview |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |

## Supported datasets

| Dataset | Modality | Patients | Access | Derived Tables |
|---------|----------|----------|--------|----------------|
| **mimic-iv-demo** | Tabular | 100 | Free | No |
| **mimic-iv** | Tabular | 365k | [PhysioNet credentialed](https://physionet.org/content/mimiciv/) | Yes (63 tables) |
| **mimic-iv-note** | Notes | 331k notes | [PhysioNet credentialed](https://physionet.org/content/mimic-iv-note/) | No |
| **eicu** | Tabular | 200k+ | [PhysioNet credentialed](https://physionet.org/content/eicu-crd/) | No |

You can also add [custom datasets](guides/custom-datasets.md).

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
