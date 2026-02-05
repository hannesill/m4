# M4 Apps: Interactive Clinical Research Tools

M4 Apps bring interactivity to clinical research workflows. While traditional MCP tools return text responses, M4 Apps render interactive UIs directly within your AI client—enabling real-time exploration, visual feedback, and iterative refinement without switching applications.

## Why Interactivity Matters for Clinical Research

Clinical research is inherently iterative. Cohort definition alone often requires dozens of refinements: adjusting age ranges, adding diagnosis codes, checking how inclusion criteria affect sample sizes. Traditional text-based interactions create friction:

- **Slow feedback loops**: Each criteria change requires a new query, waiting for results, parsing text output
- **Lost context**: Previous results disappear as new queries arrive
- **No visual comparison**: Hard to see how criteria changes affect distributions
- **Manual iteration**: Every adjustment needs explicit instructions to the AI

M4 Apps solve this by embedding purpose-built UIs for common research tasks. The UI maintains state, provides instant feedback, and surfaces patterns visually—while the underlying M4 infrastructure handles clinical semantics, SQL generation, and data access.

## Available Apps

### Cohort Builder

The Cohort Builder provides an interactive interface for defining and exploring patient cohorts. Filter by demographics, diagnoses, and clinical criteria with live updates showing how each filter affects your cohort.

**Features:**
- Real-time patient and admission counts as you adjust criteria
- Age range sliders with distribution visualization
- Gender selection with breakdown charts
- ICD code filtering with flexible matching (any/all codes)
- ICU stay and mortality filters
- Visual demographics breakdown (age distribution, gender split)
- Generated SQL available for reproducibility

**Usage:**
Simply ask your AI assistant to "open the cohort builder" or "help me define a patient cohort" when using a host that supports MCP Apps (like Claude Desktop).

```
User: I need to build a cohort of elderly diabetic patients
Claude: [Launches Cohort Builder UI]
        The cohort builder is ready. You can use the interactive UI to:
        - Set age range (you might want 65+)
        - Filter by ICD codes for diabetes
        - Add any additional criteria

[User interacts with sliders, checkboxes, sees live count updates]
```

**Supported Datasets:** MIMIC-IV, MIMIC-IV Demo

## How M4 Apps Work

M4 Apps use the MCP Apps protocol to serve interactive UIs alongside tool responses. When you call an app tool:

1. **Tool returns data**: The backend tool processes the request and returns structured data
2. **UI renders**: The host (Claude Desktop, etc.) renders the app's UI in an iframe
3. **Bidirectional communication**: The UI calls backend tools (like `query_cohort`) for live updates
4. **Results stay in context**: The AI sees the final results for follow-up questions

```
┌─────────────────────────────────────────────────────────┐
│                     Claude Desktop                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │                    Chat                           │   │
│  │  User: Build me a cohort of sepsis patients      │   │
│  │  Claude: [Launches Cohort Builder]               │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Cohort Builder UI                    │   │
│  │  ┌──────────┐ ┌───────────────────────────────┐  │   │
│  │  │ Filters  │ │ Live Results                  │  │   │
│  │  │ Age: 18+ │ │ Patients: 2,847               │  │   │
│  │  │ Gender:  │ │ Admissions: 4,213             │  │   │
│  │  │ [✓] ICU  │ │ [Age Distribution Chart]      │  │   │
│  │  │ ICD: ... │ │ [Gender Breakdown]            │  │   │
│  │  └──────────┘ └───────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
           │                         │
           │ MCP Protocol            │ Tool calls
           ▼                         ▼
┌─────────────────────────────────────────────────────────┐
│                    M4 MCP Server                         │
│  cohort_builder (launches UI)                           │
│  query_cohort (handles live updates)                    │
└─────────────────────────────────────────────────────────┘
```

## Requirements

M4 Apps require:
- **Host support**: A client that implements the MCP Apps protocol (Claude Desktop 1.x+)
- **M4 initialized**: An active dataset (`m4 init mimic-iv-demo`)
- **MCP connection**: M4 configured in your client (`m4 config claude --quick`)

Apps gracefully degrade in hosts without MCP Apps support—you'll get text-based results instead of the interactive UI.

## Interactivity Benefits by Use Case

| Research Task | Text-Only Approach | With M4 Apps |
|--------------|-------------------|--------------|
| **Cohort Definition** | Multiple query iterations, parsing counts from text | Drag sliders, instant count updates |
| **Inclusion Criteria** | Ask AI to modify SQL each time | Toggle checkboxes, see impact immediately |
| **Demographics Review** | Request statistics, read tables | Visual charts update as you filter |
| **Sample Size Planning** | Trial and error with queries | Real-time feedback on criteria tradeoffs |

## Coming Soon

M4 Apps are a new capability and the library is growing. Planned apps include:

- **Event Timeline Viewer**: Visualize patient events chronologically
- **Cohort Comparison**: Side-by-side comparison of multiple cohorts
- **Data Quality Dashboard**: Surface missing data, outliers, distributions

## Technical Details

For developers interested in building M4 Apps:

- Apps live in `src/m4/apps/`
- Each app has a tool class (Python) and UI bundle (HTML/TypeScript)
- UIs are built with Vite and bundled as single-file HTML
- Apps use the MCP Apps SDK for host communication
- Backend tools handle data queries; UIs handle presentation

See `src/m4/apps/cohort_builder/` for the reference implementation.
