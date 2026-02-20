# First Analysis

This tutorial walks you through a complete clinical data analysis session using M4. You'll explore the database, ask progressively complex questions, and understand what's happening behind the scenes.

**Prerequisites:** Complete the [Getting Started](index.md) guide (M4 installed, demo dataset initialized, AI client connected).

---

## 1. Explore the database

Start by understanding what data is available. Open your AI client and ask:

> *"What tables are available in the database?"*

M4 will return a list of tables with row counts. You should see tables like `mimiciv_hosp.admissions`, `mimiciv_hosp.patients`, `mimiciv_icu.icustays`, and more.

Next, inspect a specific table:

> *"Show me the columns in the patients table"*

This returns column names, data types, and sample data — helping you understand what information each table contains.

## 2. Ask your first clinical question

Try a simple query:

> *"What is the gender distribution in hospital admissions?"*

The AI will write and execute a SQL query, returning a summary like:

| gender | count |
|--------|-------|
| M | 185 |
| F | 165 |

## 3. What happened behind the scenes

When you asked that question, here's what M4 did:

```
You: "What is the gender distribution in hospital admissions?"
 │
 ▼
AI Client (Claude Desktop, etc.)
 │  Interprets your question
 │  Decides to use M4's execute_query tool
 ▼
M4 MCP Server
 │  Receives the SQL query
 │  Validates it (read-only, no harmful operations)
 │  Executes against the local DuckDB database
 ▼
Results returned to AI
 │  AI formats and explains the results
 ▼
You see the answer
```

M4 acts as a bridge between your AI client and the clinical database. The AI writes the SQL; M4 executes it safely and returns the results.

## 4. Progressively harder questions

Try these in order, each building on the previous:

**Basic query:**

> *"How many patients are in the database?"*

**Filtering:**

> *"Show me patients older than 65"*

**Aggregation:**

> *"What are the most common diagnoses? Show the top 10 by frequency."*

**Joins across tables:**

> *"For patients who had an ICU stay, what was their average length of stay?"*

**Clinical analysis:**

> *"What is the in-hospital mortality rate? How does it differ by gender?"*

**Complex analysis:**

> *"Find the top 5 most common diagnosis codes among patients who died during their hospital stay, and compare with the top 5 among survivors."*

!!! tip
    Don't worry about SQL syntax. Describe what you want in plain English and the AI will handle the translation. If the results don't look right, ask follow-up questions to refine.

## 5. Working with clinical notes

If you have MIMIC-IV-Note set up, you can also explore clinical narratives:

> *"Switch to the mimic-iv-note dataset"*

> *"Search for notes mentioning diabetes"*

> *"List all notes for patient 10000032"*

> *"Show me the full discharge summary for that patient"*

Notes provide rich clinical context that structured tables can't capture — treatment rationale, clinical reasoning, patient progress, and more.

## 6. Using the Python API

For more complex analyses, M4 provides a Python API that returns pandas DataFrames. If you're using Claude Code or another tool with code execution:

```python
from m4 import set_dataset, execute_query

set_dataset("mimic-iv-demo")

# Get patient demographics
patients = execute_query("""
    SELECT gender, anchor_age, anchor_year_group
    FROM mimiciv_hosp.patients
""")

# Use pandas for analysis
print(f"Total patients: {len(patients)}")
print(f"Average age: {patients['anchor_age'].mean():.1f}")
print(patients.groupby('gender')['anchor_age'].describe())
```

See the [Code Execution Guide](../guides/code-execution.md) for the full API reference.

## 7. Where to go from here

| Goal | Next step |
|------|-----------|
| Set up a larger dataset | [Datasets Guide](datasets.md) |
| Run complex analyses with Python | [Code Execution](../guides/code-execution.md) |
| Use validated clinical concepts (SOFA, sepsis, AKI) | [Skills](../guides/skills.md) |
| Access data in the cloud | [BigQuery](../guides/bigquery.md) |
| Build interactive cohort UIs | [M4 Apps](../guides/apps.md) |
| Understand M4's architecture | [Architecture](../reference/architecture.md) |
| Fix something that isn't working | [Troubleshooting](../troubleshooting.md) |
