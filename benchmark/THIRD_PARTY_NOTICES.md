# Third-Party Notices

M4Bench includes benchmark code, task definitions, evaluation harnesses, and
skill snapshots under the repository MIT license.

Ground-truth SQL and several clinical concept conventions are adapted from
MIT-LCP MIMIC-Code and eICU-Code concepts, which are MIT-licensed. Task-level
lineage is documented in `benchmark/tasks/*/PROVENANCE.yaml`, and SQL files
retain task-specific attribution headers where applicable.

MIMIC-IV v3.1 and eICU-CRD v2.0 are credentialed PhysioNet datasets governed by
their respective data-use agreements. M4Bench review artifacts do not
redistribute source EHR databases or generated task DuckDB databases; full
reconstruction requires independent PhysioNet credentialed access.
