# vitrine Server

A local display server that acts as a visualization backend for code execution agents. When an agent (Claude Code, Cursor, etc.) runs analysis in Python, it calls `show()` to push visualizations to a browser tab — no file juggling, no CLI limitations.

## How It Works

```
Agent writes Python    →    show(obj)    →    Artifact Store    →    Browser tab
                            localhost         + WebSocket            live render

from m4.vitrine import show

df = execute_query("SELECT age, gender, COUNT(*) ...")
show(df)                          # interactive table

fig = px.histogram(df, x="age")
show(fig)                         # plotly chart

show("## Key Finding\nMortality is 23% in this cohort")  # markdown card
```

Each `show()` call appends a card to a persistent browser canvas. Large objects (DataFrames, charts) are persisted in an artifact store on disk; the WebSocket sends lightweight references. Tables are paged server-side — no browser crashes, no data size limits.

## Architecture

```
src/m4/vitrine/
├── __init__.py          # Public API: show(), start(), stop()
├── server.py            # Starlette + WebSocket server
├── renderer.py          # Object → display payload conversion
├── artifacts.py         # Artifact store (disk-backed, paged access)
├── redaction.py         # PHI/PII guardrails
├── static/
│   ├── index.html       # Single-page frontend (self-contained, no build step)
│   └── vendor/          # Vendored JS (Plotly, marked) for offline use
└── _types.py            # DisplayPayload, CardType, DisplayEvent
```

### Core Concepts

**Artifact Store**: Large objects are written to disk as Parquet/JSON/SVG. The WebSocket sends a card descriptor (artifact ID, schema, preview rows). The frontend requests pages via REST. Storage layout: `{m4_data}/vitrine/runs/{YYYY-MM-DD}_{HHMMSS}_{label}/` with `index.json` (card descriptors), `meta.json` (run metadata), and `artifacts/` directory.

**Runs**: The primary organizational unit — each run represents a research question or analysis. Agents tag cards with `run_id` to group outputs. Runs persist on disk across server restarts and sessions. The frontend browses all historical runs grouped by date.

**PHI Guardrails**: On by default. Columns matching identifier patterns (names, addresses, SSN, etc.) are masked, row counts are capped. Configurable via `M4_VITRINE_REDACT`, `M4_VITRINE_MAX_ROWS`, `M4_VITRINE_HASH_IDS` env vars. Disable for de-identified datasets.

**Selections**: Researchers select table rows (checkboxes) and chart points while browsing. Selections sync to the server in real time. The agent reads them via `get_selection(card_id)` whenever it needs — no blocking, no polling.

**Decision Cards & Freeze Mechanic**: Cards pushed with `wait=True` are decision cards — they ask the researcher to make a choice. The card shows Confirm/Skip buttons, an optional text field for steering, and optional Quick Action buttons. Once confirmed, the card freezes into a static journal entry recording the decision. The frozen card becomes a permanent provenance record.

## Python API

```python
def show(obj, title=None, description=None, *, run_id=None,
         source=None, replace=None, position=None,
         wait=False, prompt=None, timeout=300,
         actions=None) -> str | DisplayResponse:
    """Push any displayable object to the browser.

    Returns card_id (fire-and-forget) or DisplayResponse (blocking).

    Supported types:
    - pd.DataFrame → interactive table (artifact-backed, paged)
    - plotly Figure → interactive chart
    - matplotlib Figure → static chart (SVG)
    - str → markdown card
    - dict → formatted key-value card
    - PIL.Image → image display
    - Form → structured input card (freezes on confirm)

    Key args:
        run_id: Group cards into a named run.
        replace: Card ID to update instead of appending.
        wait: Block until user responds in the browser.
        prompt: Question shown to user when wait=True.
        actions: Named response buttons for blocking cards (e.g. ["Approve", "Narrow further"]).
    """

def start(port=7741, open_browser=True, mode="thread") -> None
def stop() -> None
def section(title, run_id=None) -> None
def export(path, format="html", run_id=None) -> None

# Run management
def list_runs() -> list[dict]
def delete_run(run_id) -> None
def clean_runs(older_than="7d") -> int

# Selection & interaction
def get_selection(card_id) -> pd.DataFrame        # Current row/point selection for a card
def on_event(callback) -> None                    # Register callback for UI events
def run_context(run_id) -> dict                   # Structured summary of run state for agent re-orientation
```

Auto-start: `show()` calls `start()` if the server isn't running. Default mode is background thread; `mode="process"` for notebook/sandbox environments.

## Server

Starlette app (WebSocket + REST), binds to `127.0.0.1` only. Port auto-discovery: 7741–7750.

```
GET  /                              → index.html
WS   /ws                            → bidirectional display channel
GET  /api/cards?run_id=...          → card descriptors
GET  /api/table/{id}?offset&limit&sort&asc → table page
GET  /api/table/{id}/stats          → column statistics
GET  /api/table/{id}/export         → CSV export
GET  /api/table/{id}/selection      → current row selection
GET  /api/artifact/{id}             → raw artifact
GET  /api/runs                      → list runs
DELETE /api/runs/{run_id}           → delete run
GET  /api/runs/{run_id}/export      → export run
GET  /api/runs/{run_id}/context     → structured run summary for agent
POST /api/command                   → push card/section (bearer auth)
POST /api/shutdown                  → graceful shutdown (bearer auth)
```

Frontend: single self-contained HTML file, no build step, vendored JS (Plotly.js, marked.js) for offline use in hospital networks. Cards stack chronologically with collapse/pin/copy controls, server-side table paging, dark/light theme, run history dropdown, export controls. The browser is a passive visualization surface — researchers view results and make selections, but all instructions go through the terminal.

## CLI

```bash
m4 vitrine                # Start server, open browser
m4 vitrine --port 7742    # Custom port
m4 vitrine --no-open      # Start without opening browser
m4 vitrine --status       # Show server status
m4 vitrine --stop         # Stop server (runs persist on disk)
m4 vitrine --list         # List all runs
m4 vitrine --clean 7d     # Remove runs older than 7 days
m4 vitrine --export path --format html --run <run_id>  # Export
```

## Implementation Status

All phases are implemented. The display server is a fully functional research journal with:

- **Data layer**: Artifact store (Parquet/JSON on disk, DuckDB-backed paging), renderer, PHI redaction
- **Server + API**: Starlette WebSocket + REST server, `show()`/`start()`/`stop()`/`section()`/`export()` API with auto-start, port auto-discovery (7741–7750), PID file discovery, bearer token auth, multi-process `show()` via REST, CLI command
- **Frontend**: Single self-contained HTML (no build step), dark/light theme, card chrome (collapse, pin, copy, provenance), run filter dropdown, auto-reconnect, column sorting, row count badges, vendored JS (Plotly.js, marked.js) for offline use
- **Charts**: Plotly (interactive, lazy-loaded) and matplotlib (SVG, sanitized, 2MB cap), Plotly point selection events
- **Tables**: Server-side sort/filter/search via DuckDB on Parquet, column stats, CSV export, row detail panel, scroll cap with sticky header
- **Agent-human interaction**: Fire-and-forget, decision cards (`wait=True`), card replacement, row/point selection tracker, timeout/skip handling
- **Run persistence**: Run directory layout, global registry, `list_runs()`/`delete_run()`/`clean_runs()` API, REST + CLI for run CRUD, date-grouped run history browser with inline renaming, auto-select most recent run
- **Export**: Self-contained HTML export (inlined JS, table data, provenance), JSON export (card index + raw artifacts), Python API, REST endpoints, frontend Export dropdown (HTML/JSON/Print), per-run export, print-optimized CSS, CLI flags
- **Form cards**: 10 field primitives (Dropdown, MultiSelect, Slider, RangeSlider, Checkbox, Toggle, RadioGroup, TextInput, DateRange, NumberInput), `Form([...])` grouping, `.values` dict response, hybrid data+controls cards (`controls=`), freeze rendering, export support

## Interaction Model

The display draws a clear line between two surfaces:

```
Browser (passive)              Terminal (active)
──────────────────             ──────────────────
View cards & results           Give instructions to the agent
Select rows / chart points     Read agent output
Respond to blocking prompts    Start new analyses
                               Call get_selection() to read browser state
```

**The browser is a research journal, not a chat client.** Researchers view results, make selections, and respond to structured prompts. All free-form instructions go through the terminal, where the agent already has a conversation interface.

**Three interaction modes:**

1. **Push (agent → browser)** — `show()` appends cards. Fire-and-forget. The researcher sees results appear in real time. No response needed.

2. **Decide (agent ↔ browser)** — `show(obj, wait=True)` pushes a decision card and waits until the researcher responds. The card shows Confirm/Skip buttons, an optional text field for steering, and optional Quick Action buttons (`actions=["Approve", "Narrow further"]`). The response flows back as a `DisplayResponse` with action, message, selected rows, and form values.

3. **Pull (agent ← browser)** — `get_selection(card_id)` reads the researcher's current selection from any card (checked table rows, clicked chart points). The researcher selects passively while browsing; the agent reads selections whenever it needs them.

No async message queue, no polling, no "Send to Agent" button. Every interaction is either push, a synchronous block, or a pull. The agent never needs to wonder when to check for messages.

## Design Decisions

- **Not Jupyter/Streamlit/Gradio** — agents execute Python directly, not notebooks. The display is a feed, not an app. No layout system, no application state, no build step. `show(df)` works with zero setup.
- **Artifact store from day 1** — enables server-side paging, trivial export, reproducible runs, and safe large DataFrames. Retrofitting would be painful.
- **WebSocket over SSE** — bidirectional event channel (UI → agent). Starlette makes it trivial.
- **Offline-first / vendored JS / single HTML** — hospital networks block CDNs. Vendored Plotly.js + marked.js guarantee it works anywhere. No npm/build step needed.
- **Thread + process modes** — background thread by default; `mode="process"` for notebooks (event loop conflicts), sandboxes, and long-running sessions.
- **Runs over sessions** — researchers think in research questions, not server processes. Persistent `run_id` directories make the display a research journal that survives restarts.
- **Freeze-on-confirm** — interactive elements serve decision-making, the journal records the decision. Without freeze: stale widgets, dashboard creep, broken provenance.
- **Form primitives over iframes** — JSON spec is simpler, faster, more reliable for structured inputs. ~10 primitives cover 90% of agent-researcher interaction patterns.

## Provenance

Cards carry optional provenance: `show(df, source="mimiciv_derived.icustay_detail")` auto-captures source, active dataset, timestamp, query (if from `execute_query`), and optional code hash. Shown as card footer and included in exports.

## Relationship to MCP Apps

| | Display Server | MCP Apps |
|---|---|---|
| **For** | Code execution agents (CLI) | MCP hosts (Claude Desktop) |
| **Trigger** | `show()` in Python | LLM invokes MCP tool |
| **Tables** | Artifact-backed, server-side paging | Inline JSON, client-side |
| **Lifecycle** | Persistent research journal | Persistent app, part of MCP |
| **Frontend** | Single HTML + vendored JS | Vite bundle, TypeScript |

## Dependencies

No new deps — starlette, uvicorn, websockets transitive via fastmcp; pandas, duckdb already direct. Optional: plotly, matplotlib, Pillow. Vendored: plotly.js (~3.5MB), marked.js (~40KB), lazy-loaded.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Port conflict | Auto-discovery 7741-7750 |
| Browser unavailable | Cards buffer in artifact store, replay on connect |
| Large DataFrames | Artifact store + server-side paging; row limit |
| PHI exposure | Redaction on by default, explicit opt-out |
| SVG injection | Sanitize (strip `<script>`, 2MB limit) |
| Notebook thread conflicts | `mode="process"` spawns separate daemon |

## TODO

### Remove "Send to Agent" and async request queue

The "Send to Agent" button and `pending_requests()` polling pattern are broken for turn-based CLI agents. The agent has no event loop, so async messages queue silently with no feedback to the researcher. Replace with passive selection tracking and better blocking cards.

**Remove:**
- [ ] "Send to Agent" button and popover from card headers (frontend)
- [ ] `pending_requests()` and `DisplayRequest` from Python API
- [ ] Request queue on disk (`requests.json`), `store_request()` / `list_requests()` / `acknowledge_request()` in RunManager
- [ ] `GET /api/requests`, `POST /api/request_ack` server endpoints
- [ ] `on_send` parameter from `show()`

### Selection tracker

Researchers naturally select rows and chart points while browsing. Make these selections available to the agent at any time via `get_selection(card_id)`, without requiring a blocking response.

- [ ] Sync row checkbox state from browser to server on every toggle (lightweight WebSocket message: `{type: "vitrine.selection", card_id, selected_indices}`)
- [ ] Server stores per-card selection state in memory (and optionally in run directory for persistence)
- [ ] `GET /api/table/{id}/selection` endpoint returns current selection as JSON or Parquet
- [ ] `get_selection(card_id)` Python API reads current selection without blocking
- [ ] Plotly point selections feed the same tracker
- [ ] Selection persists across page changes (cross-page selection for paginated tables)
- [ ] Visual indicator on cards with active selections (badge or highlight)

### Quick Actions on decision cards

Structured response buttons beyond Confirm/Skip, so the researcher can steer the agent without typing.

- [ ] `actions=` parameter on `show()` — list of named buttons (e.g. `["Approve", "Narrow further", "Show demographics"]`)
- [ ] Frontend renders action buttons in the decision card footer
- [ ] Clicked action name returned in `DisplayResponse.action` (instead of just "confirm"/"skip")
- [ ] Text field remains available alongside actions for free-form steering

### Run context API

Let the agent re-orient after long blocking calls or at the start of a new turn. A structured summary of everything that's happened in a run.

- [ ] `run_context(run_id)` Python API — returns dict with cards shown, decisions made, current selections, pending responses
- [ ] `GET /api/runs/{run_id}/context` REST endpoint
- [ ] Includes: card titles/types/timestamps, response actions/messages/values, selection state, card count

### Browser notifications

Desktop notifications when the agent pushes a decision card, so the researcher knows to switch to the browser tab.

- [ ] `Notification.requestPermission()` on first decision card
- [ ] Desktop notification with card title/prompt when decision card arrives
- [ ] Only fire when browser tab is not focused (respect `document.hidden`)

### Agent status bar

Show the agent's current state in the browser header so the researcher knows what's happening.

- [ ] `set_status(message)` Python API — pushes a lightweight status to the browser
- [ ] Browser header shows status: "Agent is working...", "Waiting for your response", "Idle"
- [ ] WebSocket message type `vitrine.status` — no persistence, purely ephemeral
- [ ] Auto-set "Waiting for your response" when a decision card is pushed

### Deep-link URLs

Let the agent output clickable links to specific runs.

- [ ] `http://localhost:7741/#run=sepsis-v1` auto-selects the run in the dropdown
- [ ] Frontend reads `location.hash` on load and on hashchange
- [ ] `show()` return value includes URL with fragment when a run_id is set

### Skill and prompt improvements

Teach the agent optimal patterns for using the display in a CLI context.

- [ ] Update m4-vitrine skill: remove `pending_requests()` references, document selection tracker and Quick Actions
- [ ] Add context-saving patterns: "Use `show()` instead of `print()` for DataFrames — the browser handles rendering, keep terminal output minimal"
- [ ] Add guidance on blocking vs. fire-and-forget: when to use `wait=True`, how to batch results before blocking
- [ ] Instruct agent to call `run_context()` at the start of each research phase to re-orient
