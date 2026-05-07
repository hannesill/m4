# paper review Paper Regeneration Scripts

This directory contains the paper-facing scripts, frozen planning manifests,
generated tables, and review-artifact packaging code used for the paper review
submission. It is self-contained for benchmark-release review: by default,
scripts read and write under this directory. Set `M4BENCH_PAPER_DIR` only when
intentionally regenerating outputs into a separate manuscript checkout.

## Layout

```text
scripts/
  make_release_metadata.py      # task inventory, asset/license tables, artifact hash manifest
  make_final_results.py         # final primary/supplementary result tables and final run CSVs
  make_followup_manifest.py     # canonical May 6 validity-follow-up run selection
  make_followup_tables.py       # operational-spec and schema-skill follow-up tables
  package_review_artifact.py    # manifest-verified review/audit artifact archive
  package_source_release.py     # git-file source archive with double-blind redaction
  make_codex_tables.py          # legacy Codex table generator for a single analysis root
  make_pilot_tables.py          # pilot-era table generator retained for provenance
figures/
  make_figures.py               # manuscript figure regeneration
planning/                       # frozen run manifests, hash manifests, summaries
tables/                         # generated LaTeX tables used by the submission
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
`oss-rerun-provider-comparison-20260504_170533`. The packaged review artifact
stores these roots under `runs/` campaign folders for audit. For local
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

To build the review/audit archive:

```bash
python benchmark/release/v1/scripts/package_review_artifact.py --dry-run
M4BENCH_REDACTION_TERMS_FILE=/path/to/double_blind_terms.txt \
python benchmark/release/v1/scripts/package_review_artifact.py \
  --include-claude \
  --include-oss \
  --output "benchmark/release/v1/dist/m4bench-paper-results-artifact.tar.zst"
```

The archive contains paper-facing run outputs and trace artifacts for audit. It
does not redistribute MIMIC-IV, eICU, or generated task databases; full database
reconstruction requires independent PhysioNet credentialed access. The default
archive includes Codex primary and Codex follow-up runs. Use `--include-claude`
for the supplementary Claude sentinel artifacts and `--include-oss` for the
exploratory local OSS artifacts, which are labeled as non-paper-facing evidence
inside the archive README.

The submitted review artifact is available at:

```text
https://mega.nz/file/ZvMVmIJa#BKeEMt7IW2Nq6XImBHqwdswSEJ6a8nq0JUZmcA7Az8o
```

```text
Filename: m4bench-paper-results-artifact.tar.zst
Size: 17,061,661,295 bytes
SHA-256: 99f78557878d642dd9d78544e44bb3697ca7b6a7dd9ff6c4e9fe5be0e06c2b3d
```

To build an anonymous source archive for double-blind review, use the
git-file packager rather than a recursive tar command:

```bash
M4BENCH_REDACTION_TERMS_FILE=/path/to/double_blind_terms.txt \
python benchmark/release/v1/scripts/package_source_release.py --dry-run
M4BENCH_REDACTION_TERMS_FILE=/path/to/double_blind_terms.txt \
python benchmark/release/v1/scripts/package_source_release.py \
  --output "benchmark/release/v1/dist/m4bench-source-review.tar.gz"
```

This source packager uses `git ls-files`, so `.git/`, ignored credentials,
`.env`, `.DS_Store`, caches, generated databases, and untracked local planning
notes are excluded by construction. For anonymous review it omits
`CITATION.cff` by default and redacts emails, local paths, copyright holder
lines, and configured author/institution terms from text files.

Non-dry-run packaging also writes:

```text
<archive>.sha256
<archive>.manifest.json
```

Submit the archive URL together with these sidecars so reviewers can verify the
byte size, SHA-256 hash, compression mode, file counts, and selected run counts
before unpacking.

For double-blind review, provide `M4BENCH_REDACTION_TERMS` as a comma-separated
list or `M4BENCH_REDACTION_TERMS_FILE` as a newline-separated file containing
author, institution, and local account terms to redact from packaged text
artifacts. Keep that terms file outside the release repository.
