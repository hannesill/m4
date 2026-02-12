# Studies — Unifying the Journal and File Artifacts

## Naming: "study", not "run"

The organizing unit is a **study** — a research question investigated over one or more agent conversations. "Run" sounds like a single execution. "Session" implies a single sitting. "Study" is the natural clinical research term: researchers think in studies, design studies, publish studies. It scales from a 5-minute exploratory study to a multi-week multi-site validation study.

| Old | New |
|---|---|
| `run_id=` | `study=` |
| `list_runs()` | `list_studies()` |
| `delete_run()` | `delete_study()` |
| `clean_runs()` | `clean_studies()` |
| `run_context()` | `study_context()` |
| `register_output_dir(run_id=)` | `register_output_dir(study=)` |
| `export(run_id=)` | `export(study=)` |
| Runs dropdown in UI | Studies dropdown in UI |
| `{m4_data}/vitrine/runs/` | `.vitrine/studies/` |

Code reads naturally:

```python
show(df, title="Cohort", study="lactate-trajectory-v1")
section("Sensitivity Analysis", study="lactate-trajectory-v1")
ctx = study_context("lactate-trajectory-v1")
studies = list_studies()
export("output/report.html", study="lactate-trajectory-v1")
```

UI header: "Study: lactate-trajectory-v1 (47 cards, 12 files)."

## Storage: `.vitrine/`, not `m4_data/vitrine/`

Vitrine state moves from `{m4_data}/vitrine/` to a `.vitrine/` directory in the project root.

Everything in `m4_data/` is **dataset infrastructure** — DuckDB databases, downloaded Parquet files, dataset definitions, runtime config. These are the raw materials M4 operates on. Studies are **research output** — what the agent produces. They're categorically different and shouldn't share a directory.

Reasons to separate:
- **Semantics**: `m4_data/` is input (downloadable, replaceable), `.vitrine/` is output (unique, irreplaceable)
- **Gitignore**: `m4_data/` should be ignored (large Parquet files); study journals need independent ignore/include decisions
- **Lifecycle**: `m4 init` and `m4 clean` manage datasets — they shouldn't touch research output
- **Convention**: `.vitrine/` parallels `.git/`, `.venv/`, `.claude/` — a dot-directory for a tool's persistent state

`.vitrine/` replaces both `{m4_data}/vitrine/` (the current vitrine storage) and `.research/` (the m4-research skill convention). One directory for all research state.

## Problem

Studies currently produce two parallel outputs in two separate systems:

**Vitrine journal** (`.vitrine/studies/`) — the card-based research narrative. Decisions, findings, charts, tables, approval records. Machine-readable storage (index.json, artifact store). Browseable in the vitrine UI.

**File artifacts** (`.research/run_XXXXXXXX/`) — the reproducible research outputs. Numbered Python scripts, PROTOCOL.md, RESULTS.md, data/ directory with intermediate Parquet/CSV, figures/ directory with plots. Human-readable directory layout. Browseable only via terminal or Finder.

These represent the same study but live in different places, are created by different mechanisms, and are accessed through different interfaces. Neither gives the complete picture alone.

## Organizing Unit: Studies, Not Agent Conversations

A research question doesn't fit in one agent conversation. The lactate trajectory study — interview, protocol, data extraction, processing, survival analysis, cross-dataset validation — spans multiple sittings over multiple days. Each sitting is a new agent conversation. But it's one study.

**Conversation-focused (wrong):** Each agent conversation gets its own directory. The journal fragments — day 1's protocol in one directory, day 2's analysis in another, day 3's sensitivity analysis in a third. Files scatter. Export produces partial packages. The researcher mentally stitches fragments together.

**Study-focused (right):** One directory per research question, spanning multiple agent conversations. The journal is a continuous narrative. Files accumulate in one place. Export produces one complete package. The researcher opens vitrine and sees the full investigation.

The infrastructure already supports this — `study=` is a label, not tied to a conversation. Multiple conversations can use the same `study="lactate-trajectory"`. `study_context()` provides re-orientation at the start of each new conversation.

### Study lifecycle

1. **New study** — researcher describes a question → agent creates a study with a meaningful name (`study="lactate-trajectory-v1"`)
2. **Continue study** — researcher comes back → agent lists recent studies, asks which to continue, calls `study_context()` to pick up where it left off
3. **Branch study** — researcher wants a different approach → agent creates a new study (`"lactate-trajectory-v2"`) referencing the original
4. **Close study** — agent writes summary card, exports the complete journal

Agent conversations are chapters within a study — marked by `section()` dividers and `study_context()` re-orientation calls, not by separate directories. The study is the primary organizing unit. A conversation is just "when I sat down to work on it."

### What changes in prompting

The m4-research skill needs to:
- **At study start**: create a `study` name and use it consistently across all `show()` calls
- **At conversation start**: check `list_studies()` for recent studies, ask the researcher if they want to continue one, call `study_context()` to re-orient
- **Within a study**: use `section()` to mark phase transitions, not new studies
- **At study end**: show a summary card and call `export()`

## Solution

Vitrine becomes the single interface for a complete study. The journal (cards) and the file artifacts (scripts, data, figures, protocol) are both accessible from the browser.

### What changes

1. **`register_output_dir(path, study)`** — the agent registers a file directory with a study. Vitrine watches that directory and exposes its contents.

2. **Files panel in vitrine UI** — a tab or collapsible panel alongside the journal feed. Lists files in the registered output directory. Click to preview, click to download.

3. **Preview support** — images render inline, markdown renders as formatted text, code gets syntax highlighting, CSV/Parquet render as tables (DuckDB already available), notebooks render cells.

4. **Complete export** — `export("output/study.html", study=STUDY)` bundles the journal cards AND the research files into a single self-contained package.

5. **m4-research skill** saves files into the vitrine-managed output directory instead of a standalone `.research/` convention. The skill keeps its research methodology value (interview, protocol template, scientific integrity guardrails, bias checklists) and drops its storage convention.

### What stays the same

- Vitrine's card journal works exactly as today (show, section, wait, forms, etc.)
- The artifact store (Parquet/JSON/SVG for card data) stays machine-optimized
- File artifacts stay human-readable and re-runnable (`uv run python 01_data_extraction.py`)
- The m4-research skill keeps all its clinical methodology content

### What NOT to build

- Full file explorer (tree view, editing, drag-and-drop) — that's VS Code, out of scope
- Merged storage directories — the card artifact store and the file artifacts serve different purposes
- File management (create, delete, rename from UI) — that's for the agent/terminal

## Why This Improves Value

**One place to understand a study.** The journal says "we excluded 312 patients with ICU stay < 24h" and shows the cohort table. The Files panel shows the script that did it, the intermediate data, and the formal protocol. The researcher doesn't leave the browser.

**Accessibility for clinical researchers.** The target user wants rigorous clinical research without being a developer. `ls .research/run_20260107_182000/data/` is not their workflow. Click-to-preview in the browser is.

**Complete export.** The HTML export becomes a publishable research package: narrative + code + data + figures. Not just cards.

**Clickable provenance.** A card's `source="mimiciv_derived.icustay_detail"` could link to the extraction script. The provenance chain becomes navigable: card → script → data file.

## Before / After

| | Current | Combined |
|---|---|---|
| Journal (cards) | Vitrine browser | Vitrine browser |
| Files (scripts, data, figures) | Terminal / Finder | Vitrine Files panel |
| Protocol / Results | `.research/` markdown files | Journal cards + Files panel |
| Export | Cards only (HTML/JSON) | Complete package (cards + files) |
| Provenance | `source=` string on cards | Clickable: card → script → data |

## Directory Layout

```
.vitrine/
├── selections.json         # UI state (selected study, preferences)
├── server.json             # Server runtime state (port, pid)
└── studies/
    └── 2026-01-07_182000_lactate-trajectory/
        ├── index.json              # Card descriptors (existing)
        ├── meta.json               # Study metadata (existing)
        ├── artifacts/              # Card artifact store (existing)
        │   ├── {card_id}.parquet
        │   ├── {card_id}.json
        │   └── {card_id}.svg
        └── output/                 # Research file artifacts (new)
            ├── PROTOCOL.md
            ├── RESULTS.md
            ├── 01_data_extraction.py
            ├── 02_data_processing.py
            ├── 03_survival_analysis.py
            ├── data/
            │   ├── mimic_iv_stays.parquet
            │   └── eicu_stays.parquet
            └── figures/
                ├── km_curves.png
                └── forest_plot.png
```

Alternatively, the output directory could be anywhere on disk — `register_output_dir()` just tells vitrine where to look. This is more flexible (the agent can save files wherever makes sense) but less self-contained (the export needs to copy files in).

The top-level `.vitrine/` directory also holds non-study state: `selections.json` (UI preferences), server runtime info, etc.

## API Sketch

```python
from m4.vitrine import show, section, register_output_dir, export, study_context

STUDY = "lactate-trajectory-v1"

# Register where file artifacts will be saved
output_dir = register_output_dir(study=STUDY)  # returns path inside .vitrine/studies/
# or: register_output_dir("path/to/files/", study=STUDY)  # link external dir

# Agent saves files to output_dir
cohort_df.to_parquet(output_dir / "data" / "cohort.parquet")
(output_dir / "PROTOCOL.md").write_text(protocol_md)

# Journal cards reference the files naturally
show(cohort_df, title="Cohort", source="01_data_extraction.py", study=STUDY)

# Continue study in a new conversation
ctx = study_context(STUDY)
print(f"Cards: {ctx['card_count']}, Decisions: {len(ctx['decisions_made'])}")

# Export bundles everything
export("output/lactate-study.html", study=STUDY)  # cards + files
```

## Implementation Phases

### Phase 1 — Storage & naming refactor: DONE

Pure refactor. No new features, no new UI. Everything that exists today keeps working under new names and paths.

1. **Move vitrine storage to `.vitrine/`** — change `_get_vitrine_dir()` to resolve `.vitrine/` from the project root instead of `{m4_data}/vitrine/`. Add migration: if `{m4_data}/vitrine/` exists and `.vitrine/` doesn't, move it. Update `.gitignore`.
2. **Rename run → study across the codebase** — `run_id` → `study`, `list_runs` → `list_studies`, `run_context` → `study_context`, `runs/` → `studies/` directory, REST endpoints, frontend, etc. Keep `run_id` as a deprecated alias during transition.

**Verify:** All existing tests pass. Vitrine opens, shows existing studies, creates new ones. Data lives in `.vitrine/`. Old `{m4_data}/vitrine/` auto-migrates on first access.

### Phase 2 — Files integration

The new feature: studies gain a files panel. Backend and frontend can be developed in parallel once the `register_output_dir()` API is in place.

**Backend** (sequential):
1. **`register_output_dir()` API** — register a directory path with a study. Store in meta.json.
2. **File listing endpoint** — `GET /api/studies/{study}/files` returns file listing (name, size, type, modified).
3. **File preview endpoint** — `GET /api/studies/{study}/files/{path}` returns file content with appropriate content type. For Parquet/CSV, return as JSON table (DuckDB query). For images, return binary. For text/code/markdown, return raw text.

**Frontend** (parallel with backend after API is defined):
4. **Split HTML into modules** — see REFACTOR_HTML.md. Preparatory step before adding more frontend code.
5. **Files panel** — tab or collapsible panel in vitrine showing the file list. Click to preview, download per file and for the whole directory.

**Export** (after frontend):
6. **Export integration** — HTML export bundles journal cards and research files into a single self-contained package.

**Verify:** `register_output_dir()` returns a path; files saved there appear in the vitrine Files panel. Preview works for markdown, Python, images, CSV/Parquet. Export produces a complete HTML with embedded files.

### Phase 3 — Skill migration: DONE

Wire the m4-research skill into the new system. No vitrine code changes — this is purely skill-level.

1. **Update m4-research skill** — replace `.research/` directory convention with `register_output_dir()`. Skill saves scripts, protocol, data, and figures into the study's output directory. Keep all methodology content (interview, protocol template, bias checklists).
2. **Retire `.research/` pattern** — remove directory convention from skill, add migration note for existing `.research/` directories.

**Verify:** Running the m4-research skill produces files visible in the vitrine Files panel. No `.research/` directory created. Existing `.research/` directories still accessible but not created by new runs.
