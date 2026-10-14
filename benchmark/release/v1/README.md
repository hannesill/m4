# M4Bench Paper Regeneration and Release Scripts

This directory holds the scripts, frozen planning manifests, and generated
tables behind the NeurIPS 2026 camera-ready paper, and the code that builds,
scans, and verifies the open evidence packages. By default, scripts read and
write under this directory. Set `M4BENCH_PAPER_DIR` only when intentionally
regenerating outputs into a separate manuscript checkout.

Start with [Camera-Ready Release](#camera-ready-release) to download the
evidence packages and check the paper's tables against them.

## Layout

```text
scripts/
  make_release_metadata.py      # task inventory, asset/license tables, artifact hash manifest
  make_final_results.py         # final primary/supplementary result tables and final run CSVs
  make_followup_manifest.py     # canonical May 6 validity-follow-up run selection
  make_followup_tables.py       # operational-spec and schema-skill follow-up tables
  package_review_artifact.py    # review-phase archive packager (superseded, see below)
  make_codex_tables.py          # legacy Codex table generator for a single analysis root
  make_claude28_manifest.py     # freeze the July 2026 560-run Claude manifest (private inputs)
  make_claude28_tables.py       # July Claude tables from the manifest or packaged evidence
  make_control_subsets.py       # control-subset composition and selection timing
  repair_result_json.py         # derived valid copies of malformed historical result.json
  sanitize_artifacts.py         # sanitizer used by the packagers
  package_public_evidence.py    # open evidence packages with hash lineage
  verify_public_evidence.py     # verify a package and regenerate tables from it
  scan_public_evidence.py       # independent residual private-content scan of a package
  make_evidence_package_table.py  # package size/checksum table from archive sidecars
  make_croissant.py             # Croissant core + RAI metadata for the packages
  archive_io.py                 # streaming reads from retained .tar.zst archives
figures/
  make_figures.py               # manuscript figure regeneration
planning/                       # frozen run manifests, hash manifests, summaries
planning/claude28/              # July 2026 Claude manifest, attempt inventory, provenance
croissant/                      # Croissant metadata for the open evidence packages
huggingface/                    # dataset card for the Hugging Face copy of the packages
tables/                         # generated LaTeX tables used by the paper
```

## Path Defaults

The scripts default to this checkout as `M4BENCH_M4_DIR` and to this directory
as `M4BENCH_PAPER_DIR`. Override `M4BENCH_PAPER_DIR` only when writing into a
separate manuscript workspace:

```bash
export M4BENCH_M4_DIR=/path/to/m4
export M4BENCH_PAPER_DIR=/path/to/m4bench-paper
export M4BENCH_RESULTS_DIR=/path/to/m4/benchmark/results
```

The scripts write generated tables, figures, and planning metadata into
`$M4BENCH_PAPER_DIR`. With no override, this updates only
`benchmark/release/v1/`.

## Result Paths

The frozen scripts expect selected run directories under `benchmark/results/`
with the canonical root names embedded in the release CSVs, such as
`release-20260502-codex-v11`, `review-rerun-20260504-codex`,
`release-20260502-claude-provider`, `review-rerun-20260504-claude`, and
`oss-rerun-provider-comparison-20260504_170533`. The submission evidence
package stores these roots under `runs/<campaign>/`. For local
regeneration, either extract/copy the retained run roots back under
`benchmark/results/` with those names or set `M4BENCH_RESULTS_DIR` to a
directory containing the same root names.

## Regeneration Order

From the repository root:

```bash
python benchmark/release/v1/scripts/make_release_metadata.py
python benchmark/release/v1/scripts/make_final_results.py
python benchmark/release/v1/scripts/make_followup_manifest.py
python benchmark/release/v1/scripts/make_followup_tables.py
python benchmark/release/v1/figures/make_figures.py
```

These generators read the private run roots. Without them they exit with an
error and write nothing; from a public checkout, use
`verify_public_evidence.py` on an extracted evidence package instead (see
[Camera-Ready Release](#camera-ready-release)). `make_figures.py` needs
`matplotlib` from `benchmark/requirements-benchmark.txt`.

## Review-Phase Packager (Superseded)

`package_review_artifact.py` built the archive used during peer review in May
2026. It is kept for provenance. Do not use it for redistribution; the open
packages below supersede the review archive.

## Camera-Ready Release

Tag: `m4bench-neurips2026-camera-ready`. The tag holds the benchmark code,
these scripts, the planning manifests, and the tables used in the camera-ready
manuscript, as they stood after the last campaign. It is not a snapshot taken
before each campaign; see
[Code and skill state by campaign](#code-and-skill-state-by-campaign).

### Open evidence packages

| Package | Contents | Size (bytes) | SHA-256 |
|---|---|---:|---|
| `m4bench-evidence-submission.tar.zst` | 1,400 submitted-campaign runs (760 Codex primary, 190 Claude sentinel, 340 Codex follow-up, 110 exploratory OSS) | 7,548,717 | `f8b72940bd98cd9b2a852fa79c416310e2ed8ec7795b181941358d3b03ca708c` |
| `m4bench-evidence-claude-replication.tar.zst` | 560 canonical July 2026 Claude runs (28 tasks x Opus/Sonnet x no-skill/with-skill x 5 trials) | 6,398,244 | `4aeb5eda83090f89e5a3bf5d0e8c4568c18309efd66b496c4655e11abd13471b` |

Both archives, their `.sha256` and `.manifest.json` sidecars, and the Croissant
file are hosted in the Hugging Face dataset repository
<https://huggingface.co/datasets/hannesill/m4bench-evidence>.
The archives and checksum files are also attached to the GitHub release for
the tag.

Each package is built by `package_public_evidence.py`, which hashes every
source file and compares it with the declared manifest before transforming it
(any missing, extra, or mismatched file aborts the build):

- `output.csv` is replaced by `output_summary.json` (columns, row count, source
  SHA-256). Row-level outputs are derived from credentialed data and stay private.
- Traces and the agent stdout tail in `result.json` are sanitized structurally:
  tool and command outputs become `<REDACTED_TOOL_OUTPUT ...>` placeholders.
  An event that is not valid JSON in the source, or a truncated event at the
  start of a stdout tail, is withheld whole, because its tool output cannot be
  separated from agent text.
- Agent messages, SQL, and code are kept. In that text, credentials are
  removed, MIMIC and eICU identifiers are pseudonymized, and date-shifted
  timestamps, patient ages, and rows that start with an identifier are
  redacted. eICU stay identifiers are plain integers, so in eICU runs every
  standalone integer of six to nine digits is pseudonymized unless the same
  line marks it as a count. Local paths and user names are removed. Agent messages can still
  describe in words what the agent saw.
- Placeholder digests are keyed with a private salt, so short redacted values
  cannot be recovered by guessing.
- `metadata/public_artifact_manifest.json` records source path, source SHA-256,
  transform, and public SHA-256 for every entry.
- The submission package replaces 322 malformed `result.json` files with
  derived copies (`repair_result_json.py`); see
  `metadata/historical_result_json_repair_lineage.json`. The malformation was
  introduced by packaging-time path redaction that consumed JSON escape
  backslashes inside `agent_result` text; evaluator fields were unaffected and
  original bytes are unchanged in the private archive. The same redaction
  left 2,513 trace events that do not parse; they appear as
  `redacted_unparseable_event` entries.

`scan_public_evidence.py` checks an extracted package independently of the
sanitizer: it has its own patterns, requires every tool output to be a
placeholder and every event to parse, and looks for credentials, raw
identifiers, shifted datetimes, stated patient ages, and identifier-led rows
at every JSON nesting depth. Both packages pass it.

Croissant metadata (core + RAI): `croissant/m4bench_evidence.croissant.json`.
Its download URLs point at the Hugging Face repository.

### Verify and regenerate tables from a clean checkout

```bash
git clone https://github.com/hannesill/m4.git && cd m4
git checkout m4bench-neurips2026-camera-ready
base=https://huggingface.co/datasets/hannesill/m4bench-evidence/resolve/main
curl -LO "$base/m4bench-evidence-claude-replication.tar.zst"
curl -LO "$base/m4bench-evidence-claude-replication.tar.zst.sha256"
shasum -a 256 -c m4bench-evidence-claude-replication.tar.zst.sha256
mkdir -p evidence && zstd -dc m4bench-evidence-claude-replication.tar.zst | tar -x -C evidence
python3 benchmark/release/v1/scripts/verify_public_evidence.py evidence
python3 benchmark/release/v1/scripts/scan_public_evidence.py evidence
```

The Claude check is stdlib-only (Python 3.9 or later). The submission package
additionally needs the benchmark environment (`uv sync`), then:

```bash
curl -LO "$base/m4bench-evidence-submission.tar.zst"
curl -LO "$base/m4bench-evidence-submission.tar.zst.sha256"
shasum -a 256 -c m4bench-evidence-submission.tar.zst.sha256
mkdir -p evidence-submission && zstd -dc m4bench-evidence-submission.tar.zst | tar -x -C evidence-submission
uv run python benchmark/release/v1/scripts/verify_public_evidence.py evidence-submission
```

It runs `make_final_results.py` and `make_followup_tables.py` in
frozen-reference mode (`M4BENCH_FROZEN_REFERENCE=1`: reference row counts
from `tables/task_details.tex`, ordered-value nMAE from
`planning/secondary_metric_cache.json`, canonical run selection from the
tracked manifests) and compares 19 tables byte for byte with the tracked ones:
18 match and `codex_schema_skill_generalization.tex` is reported as not
regenerable (below).
`python3 benchmark/release/v1/scripts/make_claude28_tables.py --check` and
`python3 benchmark/release/v1/scripts/make_control_subsets.py` regenerate the
remaining camera-ready tables from tracked files.

Known limits:

- `codex_schema_skill_generalization.tex` is not regenerable from the packages:
  its transformed-schema no-skill cells come from the April 2026 campaign root
  `codex-full-20260428`, which is not retained in either archive.
- `task_details.tex`, `task_inventory.tex`, `artifact_package.tex`, and
  `compute_resources.tex` need credentialed reference outputs or the private
  run roots (`make_release_metadata.py`).
- Six tables are typeset in a narrower layout in the paper (`artifact_package`,
  `codex_control_subsets`, `codex_key_precision`, `compute_resources`,
  `evidence_packages`, `task_review_provenance`: transposed or with constant
  columns moved to the caption). The values are the ones in `tables/` here.
- Re-evaluating agent outputs needs the private archives plus regenerated
  reference outputs (`benchmark/setup.py`). Four reference CSVs used by the
  July audit (raw Sepsis-3, raw suspicion of infection, standard/raw urine-output
  rate) are not retained locally and must be regenerated.

### Commit identifiers

On 14 October 2026 the repository history was rewritten to remove one data
file that was committed and deleted on 26 March 2026 and should not have been
in the repository. Commits after that point have new identifiers; their file
contents are unchanged. This README cites current identifiers. Records written
before the rewrite keep the original identifiers: the files under `planning/`,
the scripts that label them, and the evidence packages.
`planning/commit_id_map.tsv` maps each original identifier to the current one.
The commits cited below:

| Original | Current | Commit |
|---|---|---|
| `9cb1c81e` | `4245cc81` | eight-task sentinel list (23 April) |
| `159b0a18` | `3405cc45` | task lists at the start of the primary campaign (2 May) |
| `1fcc3e30` | `5f3ac09c` | SQL-free skill text promoted (5 May) |
| `0fb7e458` | `fce2bd24` | operational-spec files (6 May) |
| `8492345e` | `949836d9` | operational-spec condition (6 May) |
| `f0f21bd6` | `f2f0299d` | `m4bench` branch tip, base of the Claude replication (15 May) |
| `6ed55907` | `a1c847a4` | release 0.5.3 (30 May) |
| `7932b0b7` | `2de5ca83` | model pinning on `main`, first commit (28 July) |
| `9aac2e4f` | `cb8134e7` | model pinning on `main`, second commit (28 July) |
| `7355bdf1` | `43aacb4d` | release 0.5.5 (15 September) |

`5f1faabb` and `c38e0986` are pre-merge commits that are kept only as patches,
under their original identifiers.

### Code and skill state by campaign

Run records hold task, condition, model, trial, timestamps, isolation checks,
evaluator results, and database fingerprints. They do not hold the git commit,
working-tree state, or container image digest, so the state each campaign ran
is reconstructed here from run timestamps (UTC) and commit author dates.

| Campaign | Results roots | Runs (UTC) | Code and skill state |
|---|---|---|---|
| Codex primary | `release-20260502-codex-v11` (590 canonical), `review-rerun-20260504-codex` (170) | 2-4 May 2026 | See "Primary campaign" below |
| Claude sentinel | `release-20260502-claude-provider` (160), `review-rerun-20260504-claude` (30) | 2-5 May 2026 | As the Codex primary campaign; the 30 reruns are raw baseline creatinine (both conditions) and standard OASIS with-skill |
| Exploratory OSS | `oss-rerun-provider-comparison-20260504_170533` (110) | 4 May 2026 | As the Codex primary campaign; non-publishable (local Ollama host exception) |
| Codex follow-up | `codex-validity-followup-20260506` (340) | 6 May 2026 | See "Follow-up" below |
| Claude replication, collaborator | `claude-28-20260726` (200) | 26-29 July 2026 | Declared base `f2f0299d` plus an uncommitted diff, Claude Code 2.1.119 |
| Claude replication, local | `rebuttal-claude-opus-sonnet-20260726` (220), `rebuttal-claude-opus-sonnet-additional-20260728` (140) | 26-30 July 2026 | One of the commits `f2f0299d` to `c38e0986` (below); Claude Code 2.1.119 in 67 runs and 2.1.220 in 293 |

**Primary campaign (2-4 May).** The run started from the task lists in
`3405cc45`. Clinician review on 3-4 May then changed agent-visible inputs of
nine tasks: the instruction of four (standard and raw baseline creatinine,
`eicu-gcs`, `mimic-gcs-24h-raw`) and the skill of five (`eicu-oasis`, standard
and raw OASIS, standard and raw SAPS II). Every affected cell was rerun on
4 May after the change, and the rerun replaces the earlier run in the analysis:
all conditions for the four instruction tasks, the with-skill condition for the
five skill tasks (170 runs). The other task files changed in that window are
`PROVENANCE.yaml` records, which agents never see.

Forty canonical with-skill runs (standard and raw urine-output rate and
vasopressor equivalents, both models) used the `skills-nosql/` text and carry
`with-skill-nosql` in their run IDs. That text marked each removed SQL
fragment with a placeholder. On 5 May, `5f3ac09c` replaced the placeholders
with written rules, made the result the only skill text, and deleted
`skills-nosql/`. The tag therefore holds a later skill text for these four
tasks than the primary Codex runs saw. The Codex follow-up and the Claude
replication used the text at the tag.

**Follow-up (6 May).** The operational-spec files and the condition were
committed in `fce2bd24` (03:38 UTC) and `949836d9` (03:46 UTC). Of the 80
canonical operational-spec runs, 22 started before the first commit and 27
before the second, so they ran from the working tree. The eight-task list they
use has been in `benchmark/matrix.py` since `4245cc81` (23 April). The
transformed-schema with-skill runs used the skills at the tag.

**Claude replication (26-30 July).** The collaborator declares base `f2f0299d`
plus an uncommitted diff that changes retry handling and task selection but
not task definitions or the evaluator; the diff, launch commands, and batch
scripts are in `planning/claude28/provenance/collaborator/`, and 17 canonical
runs predate the retry change. Local runs used one of four commits:
`f2f0299d`, `a1c847a4`, and the model-pinning commits `5f1faabb` and
`c38e0986`, which are kept as patches in
`planning/claude28/provenance/local/` and are on `main` as the rebased commits
`2de5ca83` and `cb8134e7`. Which of the four a given run used is not recorded.
Benchmark source hashes are retained there for `f2f0299d`, `a1c847a4`,
`c38e0986`, and the September release `43aacb4d`. The slice manifest retained
for `rebuttal-claude-opus-sonnet-additional-20260728` describes its last batch
of six tasks (120 runs); the root's seventh canonical task, raw SAPS II, ran
on 28 July before that manifest was written.

`benchmark/Dockerfile` pins Claude Code 2.1.119 at every one of these commits
and at the tag, yet 293 local runs report 2.1.220. How the image came to hold
2.1.220 was not recorded, so no commit reproduces that harness as written.
Claude Code also listed account-level claude.ai connectors as available tool
servers in 345 of the 560 runs (all 200 collaborator runs and 145 local runs),
and the egress allowlist admitted `mcp-proxy.anthropic.com`. No connector tool
was called in any run.

**What the tag adds.** Between `f2f0299d` and the tag, the only files that
differ under `benchmark/` outside `release/` are `matrix.py`, `run.py`, and the
two guides. Tasks, skills, reference SQL, and the evaluator are identical.

### July 2026 Claude campaign provenance

`planning/claude28/` holds the canonical manifest (run identity, evaluator
fields, recorded Claude Code version and model-slot overrides, trace-observed
models, artifact hashes, elapsed time, token usage), the inventory of 656
non-canonical attempts, and `provenance/` (collaborator launch commands, batch
scripts, uncommitted source diff against `f2f0299d`, local model-pinning
patches, benchmark source hashes). Selection policy: 11 complete tasks from
`rebuttal-claude-opus-sonnet-20260726`, 7 disjoint tasks from
`rebuttal-claude-opus-sonnet-additional-20260728`, 10 collaborator-complete
tasks from `claude-28-20260726`; quarantined attempts excluded. Harness
indicators differ across part of the campaign (Claude Code 2.1.119 vs 2.1.220;
model-slot overrides recorded vs native routing), so the full 28-task contrast
is descriptive; `tables/claude28_harness_sensitivity.tex` reports the 19-task
matched-indicator subset. Git SHA, dirty state, and container image digest were
not recorded per run.

Maintainers rebuild the manifest and packages from the private run archives:

```bash
python benchmark/release/v1/scripts/make_claude28_manifest.py \
  --collaborator-archive /path/to/claude-28-20260726_runs.tar.zst
python benchmark/release/v1/scripts/make_claude28_tables.py
python benchmark/release/v1/scripts/package_public_evidence.py claude28 \
  --output dist/m4bench-evidence-claude-replication.tar.zst \
  --collaborator-archive /path/to/claude-28-20260726_runs.tar.zst \
  --salt-file /private/sanitize_salt --private-patterns /private/redactions
python benchmark/release/v1/scripts/repair_result_json.py \
  /path/to/m4bench-paper-results-artifact.tar.zst \
  --output-dir /private/repairs --lineage /private/repair_lineage.json
python benchmark/release/v1/scripts/package_public_evidence.py historical \
  --output dist/m4bench-evidence-submission.tar.zst \
  --source-archive /path/to/m4bench-paper-results-artifact.tar.zst \
  --expected-manifest /path/to/packaged_artifact_manifest.json \
  --repairs-dir /private/repairs --repair-lineage /private/repair_lineage.json \
  --salt-file /private/sanitize_salt --private-patterns /private/redactions
python benchmark/release/v1/scripts/make_croissant.py dist
```

The Hugging Face repository holds the archives and sidecars, the Croissant
file, and `huggingface/README.md` as its dataset card.
