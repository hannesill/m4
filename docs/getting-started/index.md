# Getting Started

This guide walks you through installing M4 and running your first clinical data query. No prior experience with terminals, Python, or databases is needed.

---

## Prerequisites

Before you begin, make sure you have:

- [x] A computer running macOS, Windows, or Linux
- [x] An internet connection
- [x] About 20 minutes
- [x] [Claude Desktop](https://claude.ai/download) (or another AI client that supports MCP)

## Step 1: Open a terminal

A terminal (also called a command line) is a text-based way to interact with your computer. You type commands and press ++enter++ to run them.

=== "macOS"

    1. Press ++cmd+space++ to open Spotlight Search
    2. Type **Terminal** and press ++enter++
    3. A window with a text prompt will appear — this is your terminal

=== "Windows"

    1. Press ++win+x++ and select **Terminal** (or **PowerShell**)
    2. A window with a text prompt will appear — this is your terminal

=== "Linux"

    1. Press ++ctrl+alt+t++ (on most distributions)
    2. Or search for **Terminal** in your applications menu

!!! tip "How to paste into a terminal"
    On macOS: ++cmd+v++. On Windows/Linux: ++ctrl+shift+v++ (note the ++shift++).

## Step 2: Install uv

`uv` is a tool that manages Python and Python packages. Run one of these commands in your terminal:

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

??? info "What just happened?"
    This downloaded and installed `uv`, a fast Python package manager. It also installed Python if you didn't already have it. You only need to do this once.

After the install completes, **close and reopen your terminal** so the `uv` command is available.

## Step 3: Create a project and install M4

Run these commands one at a time (copy each line, paste it into your terminal, and press ++enter++):

```bash
mkdir my-research    # (1)!
cd my-research       # (2)!
uv init              # (3)!
uv add m4-infra      # (4)!
```

1. Creates a new folder called `my-research`
2. Enters that folder
3. Sets up a new Python project
4. Installs M4 and all its dependencies

## Step 4: Activate the virtual environment

A virtual environment keeps M4's dependencies separate from the rest of your system. You need to activate it each time you open a new terminal session:

=== "macOS / Linux"

    ```bash
    source .venv/bin/activate
    ```

=== "Windows (PowerShell)"

    ```powershell
    .venv\Scripts\activate
    ```

!!! warning "Remember this step"
    If you close your terminal and come back later, you'll need to `cd my-research` and activate the environment again before using M4 commands.

## Step 5: Initialize the demo dataset

```bash
m4 init mimic-iv-demo
```

This downloads the free MIMIC-IV demo dataset (~16 MB) containing 100 de-identified patient records and creates a local database. No credentials or applications are required.

??? info "What is MIMIC-IV?"
    [MIMIC-IV](https://mimic.mit.edu/) (Medical Information Mart for Intensive Care) is a large, freely-available database of de-identified health records from Beth Israel Deaconess Medical Center. The demo version contains a small subset (100 patients) that anyone can access for free. The full version (365,000+ patients) requires credentialed access through PhysioNet.

## Step 6: Connect your AI client

=== "Claude Desktop"

    ```bash
    m4 config claude --quick
    ```

    This automatically updates Claude Desktop's configuration. Restart Claude Desktop to apply.

=== "Other clients (Cursor, LibreChat, etc.)"

    ```bash
    m4 config --quick
    ```

    This prints a JSON configuration block. Copy it into your client's MCP server settings, then restart the client.

## Step 7: Ask your first question

Open Claude Desktop (or your configured AI client) and try:

> *"What tables are available in the database?"*

You should see a list of clinical data tables. Then try:

> *"Show me the gender distribution in hospital admissions"*

You're now using AI-assisted clinical data analysis.

---

## Quick version

Already comfortable with the command line? Here's the whole setup in 6 lines:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh  # Install uv (skip if you have it)
mkdir my-research && cd my-research
uv init && uv add m4-infra
source .venv/bin/activate  # Windows: .venv\Scripts\activate
m4 init mimic-iv-demo
m4 config claude --quick   # Or: m4 config --quick
```

---

## Next steps

| Goal | Guide |
|------|-------|
| Follow an end-to-end analysis tutorial | [First Analysis](first-analysis.md) |
| Set up a larger dataset (MIMIC-IV, eICU) | [Datasets](datasets.md) |
| Learn about the Python API | [Code Execution](../guides/code-execution.md) |
| Install clinical skills for your AI | [Skills](../guides/skills.md) |
| Use BigQuery instead of local files | [BigQuery](../guides/bigquery.md) |

<!-- VIDEO: Installation Walkthrough -->
!!! note "Video tutorial coming soon"
    A video walkthrough of the full installation process is planned. Check [Tutorials](../tutorials/index.md) for updates.
