---
license: mit
pretty_name: M4Bench per-run evidence
language:
  - en
tags:
  - clinical
  - ehr
  - mimic-iv
  - eicu
  - coding-agents
  - agent-traces
  - benchmark
size_categories:
  - 1K<n<10K
viewer: false
---

# M4Bench per-run evidence

Open, sanitized per-run evidence for the paper *M4Bench: Evaluating Procedural
Specification for Clinical EHR Derivation Agents* (NeurIPS 2026, Evaluations
and Datasets Track): 1,960 agent runs on 28 clinical EHR derivation tasks over
MIMIC-IV and eICU.

The benchmark itself (tasks, skills, isolation harness, evaluator, and the
scripts that build and check these packages) is the M4 repository:
<https://github.com/hannesill/m4>, tag `m4bench-neurips2026-camera-ready`.

**No patient data.** The packages contain no MIMIC-IV or eICU source data, task
databases, reference outputs, or row-level agent outputs. Rebuilding the task
databases and re-evaluating agent outputs requires independent PhysioNet
credentialed access.

## Files

| File | Runs | Contents |
|---|---:|---|
| `m4bench-evidence-submission.tar.zst` | 1,400 | May 2026 submission campaigns: 760 primary Codex, 190 Claude sentinel, 340 Codex follow-up, and 110 exploratory open-source-model runs |
| `m4bench-evidence-claude-replication.tar.zst` | 560 | July 2026 full-coverage Claude replication: 28 tasks x Opus/Sonnet x no-skill/with-skill x 5 trials |
| `*.tar.zst.sha256` | | SHA-256 checksum of each archive |
| `*.tar.zst.manifest.json` | | Size, checksum, and file counts of each archive |
| `m4bench_evidence.croissant.json` | | Croissant 1.0 metadata (core and RAI) for both archives |
| `metadata/run-indexes/*.csv` | 1,960 total | Five directly downloadable canonical run indexes, identical to the copies inside the archives |

The Croissant record sets load the CSV files in `metadata/run-indexes/` directly; no
archive extraction is needed to read the run indexes. The evidence archives
retain their existing bytes and SHA-256 checksums.

## What a run holds

- `result.json`: run identity, isolation and canary checks, evaluator results.
- `trace.jsonl`: the agent trace. Agent messages, SQL, and code are kept.
- `output_summary.json`: column names, row count, and SHA-256 of the withheld
  `output.csv`.
- `instruction.md` and `egress.jsonl`: task instruction and network egress log.
  The exploratory open-source-model runs have no egress log.

Each archive also carries `metadata/public_artifact_manifest.json`, which maps
every file to its source path, source SHA-256, transform, and public SHA-256,
and the run manifests used for the paper's tables.

## What is withheld

- Tool and command outputs, because they contain query results from
  credentialed data. Each is replaced by a placeholder with its length and a
  keyed hash prefix.
- Events that are not valid JSON in the source and truncated events at the
  start of a stdout tail. Their tool output cannot be separated from agent
  text, so the whole event is withheld (3,810 in the submission package, 559
  in the Claude package).
- In the agent text that is kept: credentials, date-shifted timestamps, patient
  ages, and rows that start with an identifier are removed, and MIMIC-IV and
  eICU identifiers are pseudonymized.

Agent messages are otherwise kept as written and can describe in words what
the agent saw.

## Download and verify

```bash
hf download hannesill/m4bench-evidence --repo-type dataset --local-dir m4bench-evidence
cd m4bench-evidence
shasum -a 256 -c m4bench-evidence-submission.tar.zst.sha256 m4bench-evidence-claude-replication.tar.zst.sha256
mkdir -p evidence-claude evidence-submission
zstd -dc m4bench-evidence-claude-replication.tar.zst | tar -x -C evidence-claude
zstd -dc m4bench-evidence-submission.tar.zst | tar -x -C evidence-submission
```

From a checkout of the tagged M4 release, each extracted package can then be
checked against its manifest, used to regenerate the paper's result tables,
and scanned for residual private content:

```bash
python3 benchmark/release/v1/scripts/verify_public_evidence.py /path/to/evidence-claude
python3 benchmark/release/v1/scripts/scan_public_evidence.py /path/to/evidence-claude
uv run python benchmark/release/v1/scripts/verify_public_evidence.py /path/to/evidence-submission
python3 benchmark/release/v1/scripts/scan_public_evidence.py /path/to/evidence-submission
```

The Claude check needs only Python 3.9 or later. The submission check needs
the benchmark environment (`uv sync`). The release README in the repository
(`benchmark/release/v1/README.md`) gives the full procedure and lists the code
and skill state behind each campaign.

## Limits

- Scores measure agreement with declared public-code reference outputs, not
  clinical correctness.
- The Claude replication harness was not uniform (two CLI versions, mixed
  model routing); the paper reports it descriptively.
- Runs record task, condition, model, trial, timestamps, and isolation checks,
  but not the source commit or container image digest.

## License

MIT, as for the M4 repository.

## Citation

```bibtex
@inproceedings{ill2026m4bench,
  title={M4Bench: Evaluating Procedural Specification for Clinical EHR Derivation Agents},
  author={Ill, Hannes and Al Attrach, Rafi and Fani, Rajna and Han, Ahram and Yamamoto, Ryohei and Moerig, Marlene Louisa and Yoon, Dukyong and Celi, Leo Anthony},
  booktitle={Advances in Neural Information Processing Systems (NeurIPS), Evaluations and Datasets Track},
  year={2026}
}
```
