#!/usr/bin/env python3
"""Write Croissant 1.0 metadata (core + RAI) for the open evidence packages.

Archive names, sizes, and SHA-256 digests come from the `.manifest.json`
sidecars written by `package_public_evidence.py`. Download URLs point at the
Hugging Face dataset repository that hosts the packages.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_io import sha256_file

RELEASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT = RELEASE_DIR / "croissant" / "m4bench_evidence.croissant.json"
TAG = "m4bench-neurips2026-camera-ready"
REPO = "https://github.com/hannesill/m4"
DATASET = "https://huggingface.co/datasets/hannesill/m4bench-evidence"
PACKAGES = {
    "m4bench-evidence-claude-replication": {
        "description": (
            "Open per-run evidence for the July 2026 full-coverage Claude campaign: "
            "560 canonical runs (28 tasks x Opus/Sonnet x no-skill/with-skill x 5 trials)."
        ),
        # Record set name, run index inside the archive, tracked copy, description.
        "run_indexes": [
            (
                "runs",
                "metadata/claude28/claude28_canonical_runs.csv",
                "planning/claude28/claude28_canonical_runs.csv",
                "One record per canonical run with evaluator reward.",
            ),
        ],
        "fields": {
            "run_id": "sc:Text",
            "task": "sc:Text",
            "condition": "sc:Text",
            "model_alias": "sc:Text",
            "trial": "sc:Integer",
            "reward": "sc:Float",
            "strict_pass": "sc:Boolean",
            "cli_versions": "sc:Text",
            "recorded_model_overrides": "sc:Boolean",
        },
    },
    "m4bench-evidence-submission": {
        "description": (
            "Open per-run evidence for the May 2026 submission campaigns: 760 primary "
            "Codex, 190 Claude sentinel, 340 Codex follow-up, and 110 exploratory OSS runs."
        ),
        "run_indexes": [
            (
                f"{campaign}-runs",
                f"metadata/planning/{csv_name}",
                f"planning/{csv_name}",
                f"One record per {runs} run with evaluator reward.",
            )
            for campaign, csv_name, runs in [
                ("codex-primary", "final_codex_runs.csv", "primary Codex"),
                ("claude-sentinel", "final_claude_runs.csv", "Claude sentinel"),
                ("codex-followup", "followup_canonical_runs.csv", "Codex follow-up"),
                ("oss-exploratory", "final_oss_runs.csv", "exploratory OSS"),
            ]
        ],
        "fields": {
            "run_id": "sc:Text",
            "task": "sc:Text",
            "condition": "sc:Text",
            "schema": "sc:Text",
            "model": "sc:Text",
            "trial": "sc:Integer",
            "reward": "sc:Float",
        },
    },
}
CONTEXT = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "containedIn": "cr:containedIn",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "prov": "http://www.w3.org/ns/prov#",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "dct": "http://purl.org/dc/terms/",
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileObject": "cr:fileObject",
    "fileProperty": "cr:fileProperty",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "sc": "https://schema.org/",
    "separator": "cr:separator",
    "samplingRate": "cr:samplingRate",
    "equivalentProperty": "cr:equivalentProperty",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}
CITATION = (
    "Ill, H., Al Attrach, R., Fani, R., Han, A., Yamamoto, R., Moerig, M. L., "
    "Yoon, D., and Celi, L. A. M4Bench: Evaluating Procedural Specification for "
    "Clinical EHR Derivation Agents. NeurIPS 2026 Evaluations and Datasets Track."
)


def distribution_and_records(package_dir: Path) -> tuple[list[dict], list[dict]]:
    distribution: list[dict] = []
    records: list[dict] = []
    for stem, spec in PACKAGES.items():
        sidecar = json.loads(
            (package_dir / f"{stem}.tar.zst.manifest.json").read_text()
        )
        archive = sidecar["archive"]
        archive_id = f"{stem}-archive"
        distribution.append(
            {
                "@type": "cr:FileObject",
                "@id": archive_id,
                "name": archive["filename"],
                "description": spec["description"],
                "contentUrl": f"{DATASET}/resolve/main/{archive['filename']}",
                "contentSize": f"{archive['size_bytes']} B",
                "encodingFormat": "application/zstd",
                "sha256": archive["sha256"],
            }
        )
        for name, runs_csv, tracked_csv, description in spec["run_indexes"]:
            record_id = f"{stem}-{name}"
            csv_id = f"{record_id}-csv"
            distribution.append(
                {
                    "@type": "cr:FileObject",
                    "@id": csv_id,
                    "name": Path(runs_csv).name,
                    "description": "Canonical run index inside the archive.",
                    "containedIn": {"@id": archive_id},
                    "contentUrl": f"{stem}/{runs_csv}",
                    "encodingFormat": "text/csv",
                    # Packaged verbatim, so the tracked file's digest applies.
                    "sha256": sha256_file(RELEASE_DIR / tracked_csv),
                }
            )
            records.append(
                {
                    "@type": "cr:RecordSet",
                    "@id": record_id,
                    "name": record_id,
                    "description": description,
                    "key": {"@id": f"{record_id}/run_id"},
                    "field": [
                        {
                            "@type": "cr:Field",
                            "@id": f"{record_id}/{column}",
                            "name": column,
                            "dataType": data_type,
                            "source": {
                                "fileObject": {"@id": csv_id},
                                "extract": {"column": column},
                            },
                        }
                        for column, data_type in spec["fields"].items()
                    ],
                }
            )
    return distribution, records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package_dir", type=Path, help="Directory with the archive sidecars."
    )
    args = parser.parse_args()
    distribution, records = distribution_and_records(args.package_dir)
    metadata = {
        "@context": CONTEXT,
        "@type": "sc:Dataset",
        "name": "M4Bench per-run evidence",
        "description": (
            "Open, sanitized per-run evidence for the M4Bench clinical EHR derivation "
            "benchmark: evaluator results, agent traces with tool outputs redacted, task "
            "instructions, network egress logs, and source-to-public hash lineage. The "
            f"benchmark itself (tasks, skills, harness, evaluator) is the M4 repository, {REPO}, "
            f"tag {TAG}."
        ),
        "conformsTo": [
            "http://mlcommons.org/croissant/1.0",
            "http://mlcommons.org/croissant/RAI/1.0",
        ],
        "citeAs": CITATION,
        "license": "https://opensource.org/licenses/MIT",
        "url": DATASET,
        "version": "1.0.0",
        "datePublished": "2026-10-13",
        "creator": [
            {"@type": "sc:Person", "name": name}
            for name in [
                "Hannes Ill",
                "Rafi Al Attrach",
                "Rajna Fani",
                "Ahram Han",
                "Ryohei Yamamoto",
                "Marlene Louisa Moerig",
                "Dukyong Yoon",
                "Leo Anthony Celi",
            ]
        ],
        "keywords": [
            "clinical EHR",
            "MIMIC-IV",
            "eICU",
            "coding agents",
            "benchmark",
            "agent skills",
        ],
        "isLiveDataset": False,
        "rai:dataLimitations": (
            "Scores measure agreement with declared public-code reference derivations, not "
            "clinical correctness. 26 of 28 tasks use MIMIC-IV and two use eICU, so the "
            "evidence is not database- or hospital-general. Row-level agent outputs and tool "
            "outputs are withheld, so outputs cannot be re-evaluated from this package alone. "
            "The July Claude campaign mixes Claude Code CLI versions and routing profiles for "
            "some tasks; see the harness sensitivity table."
        ),
        "rai:dataBiases": (
            "Task selection is critical-care focused and inherits the populations, "
            "documentation practices, and coding conventions of MIMIC-IV and eICU. Control "
            "subsets were purposively selected from pilot results and are not representative "
            "of all tasks."
        ),
        "rai:personalSensitiveInformation": (
            "Derived from de-identified credentialed PhysioNet data. The open package keeps no "
            "source data, task databases, reference outputs, row-level agent outputs, or tool "
            "outputs. Events whose tool output could not be isolated are withheld whole. In "
            "the agent text that is kept, credentials, shifted datetimes, patient ages, and "
            "identifier-led rows are removed, MIMIC and eICU identifiers are pseudonymized, "
            "and local paths and user names are removed. Agent messages can still describe in "
            "words what the agent observed."
        ),
        "rai:dataUseCases": (
            "Auditing and reproducing the M4Bench paper tables; inspecting agent behavior, "
            "failure modes, and isolation checks. Not for clinical decision-making or for "
            "estimating clinical outcomes."
        ),
        "rai:dataSocialImpact": (
            "Supports transparent evaluation of AI agents for supervised clinical research "
            "workflows. Misreading reference agreement as clinical validity could encourage "
            "unsupervised use of agent-derived clinical variables."
        ),
        "rai:hasSyntheticData": False,
        "prov:wasDerivedFrom": [
            {
                "@type": "sc:Dataset",
                "name": "MIMIC-IV v3.1",
                "url": "https://physionet.org/content/mimiciv/3.1/",
            },
            {
                "@type": "sc:Dataset",
                "name": "eICU Collaborative Research Database v2.0",
                "url": "https://physionet.org/content/eicu-crd/2.0/",
            },
        ],
        "prov:wasGeneratedBy": {
            "@type": "prov:Activity",
            "name": "M4Bench benchmark campaigns",
            "description": (
                "Docker-isolated Codex and Claude Code agent runs on per-task DuckDB clones, "
                "evaluated against hidden reference outputs, then packaged with "
                "benchmark/release/v1/scripts/package_public_evidence.py."
            ),
        },
        "distribution": distribution,
        "recordSet": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
