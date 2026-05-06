# paper review Paper Regeneration Scripts

This directory contains the paper-facing scripts used to generate M4Bench
tables, figures, metadata manifests, and the review artifact package. The
manuscript LaTeX source remains in the private sibling repository
`../m4bench-paper`; this copy is included so reviewers can inspect and rerun the
analysis code from the benchmark repository.

## Layout

```text
scripts/
  make_release_metadata.py      # task inventory, asset/license tables, artifact hash manifest
  make_final_results.py         # final primary/supplementary result tables and final run CSVs
  make_followup_manifest.py     # canonical May 6 validity-follow-up run selection
  make_followup_tables.py       # operational-spec and schema-skill follow-up tables
  package_review_artifact.py    # manifest-verified review/audit artifact archive
  make_codex_tables.py          # legacy Codex table generator for a single analysis root
  make_pilot_tables.py          # pilot-era table generator retained for provenance
figures/
  make_figures.py               # manuscript figure regeneration
```

## Path Defaults

The copied scripts default to this checkout as `M4BENCH_M4_DIR` and to the
sibling `../m4bench-paper` checkout as `M4BENCH_PAPER_DIR`. Override these when
your layout differs:

```bash
export M4BENCH_M4_DIR=/path/to/m4
export M4BENCH_PAPER_DIR=/path/to/m4bench-paper
export M4BENCH_RESULTS_DIR=/path/to/m4/benchmark/results
```

The scripts write generated tables, figures, and planning metadata into
`$M4BENCH_PAPER_DIR`. To inspect behavior without changing the manuscript
checkout, point `M4BENCH_PAPER_DIR` at a temporary copy of the paper directory.

## Regeneration Order

From the repository root:

```bash
python benchmark/release/v1/scripts/make_release_metadata.py
python benchmark/release/v1/scripts/make_final_results.py
python benchmark/release/v1/scripts/make_followup_manifest.py
python benchmark/release/v1/scripts/make_followup_tables.py
python benchmark/release/v1/figures/make_figures.py
```

To build the review/audit archive:

```bash
python benchmark/release/v1/scripts/package_review_artifact.py --dry-run
python benchmark/release/v1/scripts/package_review_artifact.py \
  --include-claude \
  --include-oss \
  --output "$M4BENCH_PAPER_DIR/dist/m4bench-paper-results-artifact.tar.zst"
```

The archive contains paper-facing run outputs and trace artifacts for audit. It
does not redistribute MIMIC-IV, eICU, or generated task databases; full database
reconstruction requires independent PhysioNet credentialed access. The default
archive includes Codex primary and Codex follow-up runs. Use `--include-claude`
for the supplementary Claude sentinel artifacts and `--include-oss` for the
exploratory local OSS artifacts, which are labeled as non-paper-facing evidence
inside the archive README.
