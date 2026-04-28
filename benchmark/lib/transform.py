"""Contamination analysis: lossless schema transformations for MIMIC-IV.

Provides three database conditions for memorization decomposition:
  1. Native — original MIMIC-IV schema
  2. Obfuscated — all schema/table/column names replaced with neutral identifiers
  3. Restructured — obfuscated names + structural changes (merged/split tables)

Key invariant: all three conditions produce identical ground truth output.

Usage:
    python -m benchmark.lib.transform build-dictionary
    python -m benchmark.lib.transform create-obfuscated
    python -m benchmark.lib.transform create-restructured
    python -m benchmark.lib.transform verify
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import duckdb

# ── Paths ──────────────────────────────────────────────────────────────────

LIB_DIR = Path(__file__).resolve().parent
BENCHMARK_ROOT = LIB_DIR.parent
REPO_ROOT = BENCHMARK_ROOT.parent

SOURCE_DB = REPO_ROOT / "m4_data" / "databases" / "mimic_iv.duckdb"
OBFUSCATED_DB = REPO_ROOT / "m4_data" / "databases" / "obfuscated_mimic_iv.duckdb"
RESTRUCTURED_DB = REPO_ROOT / "m4_data" / "databases" / "restructured_mimic_iv.duckdb"
DICTIONARY_PATH = LIB_DIR / "dictionary.json"
GROUND_TRUTH_DIR = BENCHMARK_ROOT / "ground_truth"
AGENT_DB_DIR = BENCHMARK_ROOT / "agent_db"

# ── Semantic descriptions for obfuscated instructions ─────────────────────
# These replace native MIMIC names in the dictionary section so that agents
# cannot reverse-engineer the obfuscation via mechanical find-and-replace.

_SCHEMA_DESCRIPTIONS = {
    "mimiciv_derived": "derived/computed clinical tables",
    "mimiciv_hosp": "hospital-level tables",
    "mimiciv_icu": "ICU-level tables",
}

_TABLE_DESCRIPTIONS = {
    "mimiciv_hosp.patients": "patient demographics",
    "mimiciv_hosp.admissions": "hospital admission records",
    "mimiciv_icu.icustays": "ICU stay records",
    "mimiciv_icu.chartevents": "charted clinical observations",
    "mimiciv_hosp.labevents": "laboratory test results",
    "mimiciv_icu.inputevents": "administered medications and fluids",
    "mimiciv_icu.outputevents": "measured outputs (urine, drains)",
    "mimiciv_icu.procedureevents": "procedural events",
    "mimiciv_icu.d_items": "clinical measurement definitions",
    "mimiciv_hosp.d_labitems": "laboratory test definitions",
    "mimiciv_hosp.services": "hospital service assignments",
    "mimiciv_hosp.diagnoses_icd": "coded diagnoses",
    "mimiciv_hosp.procedures_icd": "coded procedures",
    "mimiciv_hosp.transfers": "patient transfer records",
}

_COLUMN_DESCRIPTIONS = {
    "subject_id": "unique patient identifier",
    "hadm_id": "hospital admission identifier",
    "stay_id": "ICU stay identifier",
    "itemid": "measurement/item code",
    "charttime": "timestamp of charted observation",
    "starttime": "event start timestamp",
    "endtime": "event end timestamp",
    "storetime": "timestamp value was stored",
    "value": "recorded value (text)",
    "valuenum": "recorded numeric value",
    "valueuom": "unit of measurement",
    "intime": "unit admission timestamp",
    "outtime": "unit discharge timestamp",
    "admittime": "hospital admission timestamp",
    "dischtime": "hospital discharge timestamp",
    "label": "human-readable item label",
    "category": "item category",
    "gender": "patient sex",
    "anchor_age": "patient age (integer)",
    "los": "length of stay (days)",
    "admission_type": "type of admission",
    "hospital_expire_flag": "died during admission (0/1)",
    "icd_code": "diagnosis/procedure code",
    "icd_version": "ICD version (9 or 10)",
    "rate": "infusion rate",
    "rateuom": "rate unit of measurement",
    "amount": "administered amount",
    "amountuom": "amount unit of measurement",
    "patientweight": "patient weight (kg)",
    "curr_service": "current hospital service",
    "seq_num": "sequence/priority number",
    "flag": "abnormal flag",
    "specimen_id": "specimen identifier",
    "labevent_id": "laboratory result identifier",
    "caregiver_id": "clinician identifier",
    "warning": "warning indicator",
    "ref_range_lower": "reference range lower bound",
    "ref_range_upper": "reference range upper bound",
    "abbreviation": "item abbreviation",
    "linksto": "associated event table",
    "unitname": "unit name",
    "param_type": "parameter type",
    "fluid": "fluid type",
    "dod": "date of death",
    "deathtime": "time of death",
    "first_careunit": "admission unit name",
    "last_careunit": "discharge unit name",
}

# Schemas to process (skip DuckDB internal schemas)
SKIP_SCHEMAS = {"information_schema", "pg_catalog", "main"}


# ── Dictionary Generation ──────────────────────────────────────────────────


def build_dictionary(db_path: Path = SOURCE_DB) -> dict:
    """Generate a deterministic renaming dictionary from the DB schema.

    Returns a dict with keys: schemas, tables, columns, restructured_tables,
    restructured_columns. All mappings are bijective (no collisions).
    """
    con = duckdb.connect(str(db_path), read_only=True)

    # Enumerate schemas
    schemas = sorted(
        row[0]
        for row in con.execute(
            "SELECT DISTINCT table_schema FROM information_schema.columns"
        ).fetchall()
        if row[0] not in SKIP_SCHEMAS
    )

    # Enumerate tables per schema
    tables_by_schema: dict[str, list[str]] = {}
    for row in con.execute(
        "SELECT DISTINCT table_schema, table_name FROM information_schema.columns "
        "ORDER BY table_schema, table_name"
    ).fetchall():
        schema, table = row
        if schema in SKIP_SCHEMAS:
            continue
        tables_by_schema.setdefault(schema, []).append(table)

    # Enumerate all unique column names (global mapping)
    all_columns = sorted(
        set(
            row[0]
            for row in con.execute(
                "SELECT DISTINCT column_name FROM information_schema.columns "
                "WHERE table_schema NOT IN "
                "('information_schema', 'pg_catalog', 'main')"
            ).fetchall()
        )
    )

    con.close()

    # Build schema mapping: ds_1, ds_2, ds_3
    schema_map = {}
    for i, schema in enumerate(schemas, 1):
        schema_map[schema] = f"ds_{i}"

    # Build table mapping: ds_X.t_NNN (sorted within schema)
    table_map = {}
    for schema in schemas:
        for j, table in enumerate(sorted(tables_by_schema.get(schema, [])), 1):
            fqn = f"{schema}.{table}"
            obf_fqn = f"{schema_map[schema]}.t_{j:03d}"
            table_map[fqn] = obf_fqn

    # Build global column mapping: c_NNN
    column_map = {}
    for k, col in enumerate(all_columns, 1):
        column_map[col] = f"c_{k:03d}"

    # Restructured-specific: new tables and discriminator columns
    # These use high IDs (900+) to avoid collisions with original mappings.
    restructured_tables = {
        # T1: chartevents + labevents → observations
        "observations": f"{schema_map['mimiciv_icu']}.t_901",
        # T2: patients + admissions + icustays → encounters
        "encounters": f"{schema_map['mimiciv_hosp']}.t_901",
        # T3: inputevents + outputevents → flows
        "flows": f"{schema_map['mimiciv_icu']}.t_902",
        # T4: d_items + d_labitems → item_reference
        "item_reference": f"{schema_map['mimiciv_icu']}.t_903",
    }
    restructured_columns = {
        "source": "c_901",  # observations: 'chart' | 'lab'
        "direction": "c_902",  # flows: 'in' | 'out'
        "item_type": "c_903",  # item_reference: 'chart' | 'lab'
    }

    dictionary = {
        "schemas": schema_map,
        "tables": table_map,
        "columns": column_map,
        "restructured_tables": restructured_tables,
        "restructured_columns": restructured_columns,
    }

    # Sanity: verify bijectivity
    _verify_bijectivity(dictionary)

    return dictionary


def _verify_bijectivity(dictionary: dict) -> None:
    """Assert no two original names map to the same obfuscated name."""
    for section in ["schemas", "tables", "columns"]:
        mapping = dictionary[section]
        values = list(mapping.values())
        if len(values) != len(set(values)):
            dupes = [v for v in values if values.count(v) > 1]
            raise ValueError(f"Collision in {section}: {set(dupes)}")


def save_dictionary(dictionary: dict, path: Path = DICTIONARY_PATH) -> None:
    """Save dictionary to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(dictionary, f, indent=2, sort_keys=True)
    print(
        f"Dictionary saved to {path} ({len(dictionary['columns'])} columns, "
        f"{len(dictionary['tables'])} tables)"
    )


def load_dictionary(path: Path = DICTIONARY_PATH) -> dict:
    """Load dictionary from JSON."""
    with open(path) as f:
        return json.load(f)


# ── Reverse lookup helpers ─────────────────────────────────────────────────


def reverse_dict(d: dict) -> dict:
    """Create reverse mapping (obfuscated → original)."""
    return {v: k for k, v in d.items()}


def get_obfuscated_table(dictionary: dict, native_fqn: str) -> str:
    """Map a native fully-qualified table name to its obfuscated form.

    e.g., 'mimiciv_derived.sofa' → 'ds_1.t_045'
    """
    if native_fqn in dictionary["tables"]:
        return dictionary["tables"][native_fqn]
    raise KeyError(f"Table '{native_fqn}' not in dictionary")


# ── Obfuscated Database Creation ───────────────────────────────────────────


PARQUET_DIR = REPO_ROOT / "m4_data" / "parquet" / "mimic-iv"
OBFUSCATED_PARQUET_DIR = REPO_ROOT / "m4_data" / "parquet" / "obfuscated-mimic-iv"
RESTRUCTURED_PARQUET_DIR = REPO_ROOT / "m4_data" / "parquet" / "restructured-mimic-iv"


def create_obfuscated_db(
    source: Path = SOURCE_DB,
    dest: Path = OBFUSCATED_DB,
    dictionary: dict | None = None,
) -> Path:
    """Create an obfuscated copy of the MIMIC-IV database.

    Architecture mirrors the original: base tables (hosp/icu) stored as
    parquet files with renamed columns, referenced via views. Derived
    tables materialized in DuckDB with renamed columns. This keeps the
    DB size comparable to the original (~2 GB).
    """
    if dictionary is None:
        dictionary = load_dictionary()

    if dest.exists():
        dest.unlink()
    wal = dest.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()

    col_map = dictionary["columns"]

    # Phase 1: Create obfuscated parquet files for base tables (hosp/icu)
    print("Creating obfuscated parquet files ...")
    OBFUSCATED_PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    # Use a temp connection to read source and write parquet
    tmp_con = duckdb.connect()

    base_schemas = ["mimiciv_hosp", "mimiciv_icu"]
    for native_schema in base_schemas:
        obf_schema = dictionary["schemas"][native_schema]
        schema_subdir = native_schema.replace("mimiciv_", "")  # hosp, icu

        src_parquet_dir = PARQUET_DIR / schema_subdir
        dest_parquet_dir = OBFUSCATED_PARQUET_DIR / obf_schema
        dest_parquet_dir.mkdir(parents=True, exist_ok=True)

        for pq_file in sorted(src_parquet_dir.glob("*.parquet")):
            native_table = pq_file.stem
            native_fqn = f"{native_schema}.{native_table}"

            if native_fqn not in dictionary["tables"]:
                print(f"  SKIP {native_fqn} (not in dictionary)")
                continue

            obf_fqn = dictionary["tables"][native_fqn]
            obf_table = obf_fqn.split(".")[1]

            # Read parquet, rename columns, write to new location
            col_info = tmp_con.execute(
                f"SELECT name FROM parquet_schema('{pq_file}') "
                f"WHERE name != 'duckdb_schema'"
            ).fetchall()

            select_parts = []
            for (col_name,) in col_info:
                obf_col = col_map.get(col_name)
                if obf_col is None:
                    raise KeyError(
                        f"Column '{col_name}' in {native_fqn} not in dictionary"
                    )
                select_parts.append(f'"{col_name}" AS "{obf_col}"')

            dest_pq = dest_parquet_dir / f"{obf_table}.parquet"
            tmp_con.execute(
                f"COPY (SELECT {', '.join(select_parts)} FROM '{pq_file}') "
                f"TO '{dest_pq}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            row_count = tmp_con.execute(f"SELECT COUNT(*) FROM '{dest_pq}'").fetchone()[
                0
            ]
            print(f"  {native_fqn} → {dest_pq.name} ({row_count:,} rows)")

    tmp_con.close()

    # Phase 2: Create DuckDB with views over obfuscated parquets + materialized derived
    print(f"\nCreating obfuscated DB: {dest}")
    con = duckdb.connect(str(dest))

    # Create schemas
    for native_schema, obf_schema in dictionary["schemas"].items():
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{obf_schema}"')

    # Create views for base tables
    for native_schema in base_schemas:
        obf_schema = dictionary["schemas"][native_schema]
        dest_parquet_dir = OBFUSCATED_PARQUET_DIR / obf_schema

        for pq_file in sorted(dest_parquet_dir.glob("*.parquet")):
            obf_table = pq_file.stem
            abs_path = pq_file.resolve()
            con.execute(
                f'CREATE VIEW "{obf_schema}"."{obf_table}" AS '
                f"SELECT * FROM read_parquet('{abs_path}')"
            )

    # Materialize derived tables from source
    print("\nMaterializing derived tables ...")
    con.execute(f"ATTACH '{source}' AS src (READ_ONLY)")

    derived_schema = "mimiciv_derived"

    for native_fqn, obf_fqn in sorted(dictionary["tables"].items()):
        if not native_fqn.startswith(derived_schema):
            continue

        native_table = native_fqn.split(".")[1]

        # Get column info from source
        sample = con.execute(f"SELECT * FROM src.{native_fqn} LIMIT 0").description
        col_names = [desc[0] for desc in sample]

        select_parts = []
        for col_name in col_names:
            obf_col = col_map.get(col_name)
            if obf_col is None:
                raise KeyError(f"Column '{col_name}' in {native_fqn} not in dictionary")
            select_parts.append(f'"{col_name}" AS "{obf_col}"')

        con.execute(
            f"CREATE TABLE {obf_fqn} AS "
            f"SELECT {', '.join(select_parts)} FROM src.{native_fqn}"
        )

        row_count = con.execute(f"SELECT COUNT(*) FROM {obf_fqn}").fetchone()[0]
        print(f"  {native_fqn} → {obf_fqn} ({row_count:,} rows)")

    con.execute("DETACH src")
    con.execute("CHECKPOINT")

    # Verify table count
    table_count = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'main')"
    ).fetchone()[0]
    con.close()

    size_gb = dest.stat().st_size / 1e9
    print(f"\nObfuscated DB created: {dest} ({size_gb:.2f} GB, {table_count} tables)")
    return dest


# ── Restructured Database Creation ─────────────────────────────────────────


def create_restructured_db(
    source: Path = OBFUSCATED_DB,
    dest: Path = RESTRUCTURED_DB,
    dictionary: dict | None = None,
) -> Path:
    """Create a restructured copy of the obfuscated MIMIC-IV database.

    Starts from the obfuscated DB and applies 4 structural transformations:
      T1: chartevents + labevents → observations
      T2: patients + admissions + icustays → encounters
      T3: inputevents + outputevents → flows
      T4: d_items + d_labitems → item_reference

    All transforms are lossless — original tables can be reconstructed.
    """
    if dictionary is None:
        dictionary = load_dictionary()

    if dest.exists():
        dest.unlink()
    wal = dest.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()

    # Start by copying the obfuscated DB
    print(f"Copying obfuscated DB to {dest} ...")
    shutil.copy2(source, dest)
    src_wal = source.with_suffix(".duckdb.wal")
    if src_wal.exists():
        shutil.copy2(src_wal, wal)

    con = duckdb.connect(str(dest))

    col = dictionary["columns"]
    tbl = dictionary["tables"]
    rtbl = dictionary["restructured_tables"]
    rcol = dictionary["restructured_columns"]

    # Helper to get obfuscated FQN
    def t(native_fqn: str) -> str:
        return tbl[native_fqn]

    def c(native_col: str) -> str:
        return col[native_col]

    # ── T1: Merge chartevents + labevents → observations ──────────────

    print("\nT1: Merging chartevents + labevents → observations ...")
    obs_tbl = rtbl["observations"]
    ce_tbl = t("mimiciv_icu.chartevents")
    le_tbl = t("mimiciv_hosp.labevents")
    src_col = rcol["source"]

    # Get chartevents columns
    ce_cols = _get_column_names(con, ce_tbl)
    le_cols = _get_column_names(con, le_tbl)

    # Shared columns (present in both)
    shared = [
        c
        for c in [
            col["subject_id"],
            col["hadm_id"],
            col["itemid"],
            col["charttime"],
            col["storetime"],
            col["value"],
            col["valuenum"],
            col["valueuom"],
        ]
    ]

    # Chart-specific columns
    chart_only = [
        c
        for c in ce_cols
        if c not in shared and c not in _get_column_names(con, le_tbl)
    ]
    # Lab-specific columns
    lab_only = [
        c
        for c in le_cols
        if c not in shared and c not in _get_column_names(con, ce_tbl)
    ]

    # stay_id is in chartevents but not labevents — handle specially
    stay_id_col = col["stay_id"]

    # Build the UNION ALL SQL dynamically
    # Chart half: all chart columns + NULL for lab-only columns
    chart_select = [f"'chart' AS \"{src_col}\""]
    # Shared columns
    for sc in shared:
        chart_select.append(f'ce."{sc}"')
    # stay_id (in chart)
    chart_select.append(f'ce."{stay_id_col}"')
    # chart-only columns
    for cc in chart_only:
        if cc != stay_id_col:
            chart_select.append(f'ce."{cc}"')
    # lab-only columns as NULL
    for lc in lab_only:
        dtype = _get_column_type(con, le_tbl, lc)
        chart_select.append(f'NULL::{dtype} AS "{lc}"')

    # Lab half: all lab columns + NULL for chart-only columns
    lab_select = [f"'lab' AS \"{src_col}\""]
    for sc in shared:
        lab_select.append(f'le."{sc}"')
    # stay_id (NULL for labs)
    lab_select.append(f'NULL::BIGINT AS "{stay_id_col}"')
    # chart-only columns as NULL
    for cc in chart_only:
        if cc != stay_id_col:
            dtype = _get_column_type(con, ce_tbl, cc)
            lab_select.append(f'NULL::{dtype} AS "{cc}"')
    # lab-only columns
    for lc in lab_only:
        lab_select.append(f'le."{lc}"')

    sql_t1 = (
        f"CREATE TABLE {obs_tbl} AS\n"
        f"SELECT {', '.join(chart_select)}\n"
        f"FROM {ce_tbl} ce\n"
        f"UNION ALL\n"
        f"SELECT {', '.join(lab_select)}\n"
        f"FROM {le_tbl} le"
    )
    con.execute(sql_t1)

    # Verify row count
    ce_count = con.execute(f"SELECT COUNT(*) FROM {ce_tbl}").fetchone()[0]
    le_count = con.execute(f"SELECT COUNT(*) FROM {le_tbl}").fetchone()[0]
    obs_count = con.execute(f"SELECT COUNT(*) FROM {obs_tbl}").fetchone()[0]
    assert obs_count == ce_count + le_count, (
        f"T1 row count: {obs_count} != {ce_count} + {le_count}"
    )
    print(
        f"  {ce_tbl} ({ce_count:,}) + {le_tbl} ({le_count:,}) = {obs_tbl} ({obs_count:,})"
    )

    # Drop originals (may be views or tables)
    _drop_table_or_view(con, ce_tbl)
    _drop_table_or_view(con, le_tbl)

    # ── T2: Denormalize patients + admissions + icustays → encounters ─

    print("\nT2: Denormalizing patients + admissions + icustays → encounters ...")
    enc_tbl = rtbl["encounters"]
    pat_tbl = t("mimiciv_hosp.patients")
    adm_tbl = t("mimiciv_hosp.admissions")
    icu_tbl = t("mimiciv_icu.icustays")

    pat_cols = _get_column_names(con, pat_tbl)
    adm_cols = _get_column_names(con, adm_tbl)
    icu_cols = _get_column_names(con, icu_tbl)

    subj_col = col["subject_id"]
    hadm_col = col["hadm_id"]

    # Build SELECT: all patient cols, all admission cols (except subject_id dup),
    # all icustay cols (except subject_id/hadm_id dups)
    enc_select = []
    # Patient columns
    for pc in pat_cols:
        enc_select.append(f'p."{pc}"')
    # Admission columns (skip subject_id — already from patients)
    for ac in adm_cols:
        if ac == subj_col:
            continue
        enc_select.append(f'a."{ac}"')
    # ICU stay columns (skip subject_id, hadm_id — already present)
    for ic in icu_cols:
        if ic in (subj_col, hadm_col):
            continue
        dtype = _get_column_type(con, icu_tbl, ic)
        enc_select.append(f'i."{ic}"')

    sql_t2 = (
        f"CREATE TABLE {enc_tbl} AS\n"
        f"SELECT {', '.join(enc_select)}\n"
        f"FROM {adm_tbl} a\n"
        f'JOIN {pat_tbl} p ON a."{subj_col}" = p."{subj_col}"\n'
        f'LEFT JOIN {icu_tbl} i ON a."{hadm_col}" = i."{hadm_col}"'
    )
    con.execute(sql_t2)

    adm_count = con.execute(f"SELECT COUNT(*) FROM {adm_tbl}").fetchone()[0]
    icu_count = con.execute(f"SELECT COUNT(*) FROM {icu_tbl}").fetchone()[0]
    enc_count = con.execute(f"SELECT COUNT(*) FROM {enc_tbl}").fetchone()[0]
    print(
        f"  {pat_tbl} + {adm_tbl} ({adm_count:,}) + {icu_tbl} ({icu_count:,}) → {enc_tbl} ({enc_count:,})"
    )
    # enc_count >= adm_count (multi-ICU admissions expand rows)
    assert enc_count >= adm_count, (
        f"T2: encounters ({enc_count}) < admissions ({adm_count})"
    )

    _drop_table_or_view(con, pat_tbl)
    _drop_table_or_view(con, adm_tbl)
    _drop_table_or_view(con, icu_tbl)

    # ── T3: Merge inputevents + outputevents → flows ──────────────────

    print("\nT3: Merging inputevents + outputevents → flows ...")
    flows_tbl = rtbl["flows"]
    ie_tbl = t("mimiciv_icu.inputevents")
    oe_tbl = t("mimiciv_icu.outputevents")
    dir_col = rcol["direction"]

    ie_cols = _get_column_names(con, ie_tbl)
    oe_cols = _get_column_names(con, oe_tbl)

    # Shared columns between input and output
    shared_io = [c for c in oe_cols if c in ie_cols]
    # Input-only columns
    input_only = [c for c in ie_cols if c not in oe_cols]
    # Output-only columns
    output_only = [c for c in oe_cols if c not in ie_cols]

    # Input half
    in_select = [f"'in' AS \"{dir_col}\""]
    for sc in shared_io:
        in_select.append(f'ie."{sc}"')
    for ic in input_only:
        in_select.append(f'ie."{ic}"')
    for oc in output_only:
        dtype = _get_column_type(con, oe_tbl, oc)
        in_select.append(f'NULL::{dtype} AS "{oc}"')

    # Output half
    out_select = [f"'out' AS \"{dir_col}\""]
    for sc in shared_io:
        out_select.append(f'oe."{sc}"')
    for ic in input_only:
        dtype = _get_column_type(con, ie_tbl, ic)
        out_select.append(f'NULL::{dtype} AS "{ic}"')
    for oc in output_only:
        out_select.append(f'oe."{oc}"')

    sql_t3 = (
        f"CREATE TABLE {flows_tbl} AS\n"
        f"SELECT {', '.join(in_select)}\n"
        f"FROM {ie_tbl} ie\n"
        f"UNION ALL\n"
        f"SELECT {', '.join(out_select)}\n"
        f"FROM {oe_tbl} oe"
    )
    con.execute(sql_t3)

    ie_count = con.execute(f"SELECT COUNT(*) FROM {ie_tbl}").fetchone()[0]
    oe_count = con.execute(f"SELECT COUNT(*) FROM {oe_tbl}").fetchone()[0]
    flows_count = con.execute(f"SELECT COUNT(*) FROM {flows_tbl}").fetchone()[0]
    assert flows_count == ie_count + oe_count, (
        f"T3 row count: {flows_count} != {ie_count} + {oe_count}"
    )
    print(
        f"  {ie_tbl} ({ie_count:,}) + {oe_tbl} ({oe_count:,}) = {flows_tbl} ({flows_count:,})"
    )

    _drop_table_or_view(con, ie_tbl)
    _drop_table_or_view(con, oe_tbl)

    # ── T4: Merge d_items + d_labitems → item_reference ───────────────

    print("\nT4: Merging d_items + d_labitems → item_reference ...")
    ref_tbl = rtbl["item_reference"]
    di_tbl = t("mimiciv_icu.d_items")
    dl_tbl = t("mimiciv_hosp.d_labitems")
    type_col = rcol["item_type"]

    di_cols = _get_column_names(con, di_tbl)
    dl_cols = _get_column_names(con, dl_tbl)

    shared_ref = [c for c in dl_cols if c in di_cols]
    di_only = [c for c in di_cols if c not in dl_cols]
    dl_only = [c for c in dl_cols if c not in di_cols]

    # d_items half
    di_select = [f"'chart' AS \"{type_col}\""]
    for sc in shared_ref:
        di_select.append(f'd."{sc}"')
    for dc in di_only:
        di_select.append(f'd."{dc}"')
    for lc in dl_only:
        dtype = _get_column_type(con, dl_tbl, lc)
        di_select.append(f'NULL::{dtype} AS "{lc}"')

    # d_labitems half
    dl_select = [f"'lab' AS \"{type_col}\""]
    for sc in shared_ref:
        dl_select.append(f'dl."{sc}"')
    for dc in di_only:
        dtype = _get_column_type(con, di_tbl, dc)
        dl_select.append(f'NULL::{dtype} AS "{dc}"')
    for lc in dl_only:
        dl_select.append(f'dl."{lc}"')

    sql_t4 = (
        f"CREATE TABLE {ref_tbl} AS\n"
        f"SELECT {', '.join(di_select)}\n"
        f"FROM {di_tbl} d\n"
        f"UNION ALL\n"
        f"SELECT {', '.join(dl_select)}\n"
        f"FROM {dl_tbl} dl"
    )
    con.execute(sql_t4)

    di_count = con.execute(f"SELECT COUNT(*) FROM {di_tbl}").fetchone()[0]
    dl_count = con.execute(f"SELECT COUNT(*) FROM {dl_tbl}").fetchone()[0]
    ref_count = con.execute(f"SELECT COUNT(*) FROM {ref_tbl}").fetchone()[0]
    assert ref_count == di_count + dl_count, (
        f"T4 row count: {ref_count} != {di_count} + {dl_count}"
    )
    print(
        f"  {di_tbl} ({di_count:,}) + {dl_tbl} ({dl_count:,}) = {ref_tbl} ({ref_count:,})"
    )

    _drop_table_or_view(con, di_tbl)
    _drop_table_or_view(con, dl_tbl)

    # ── Export merged tables to parquet for size efficiency ──────────

    print("\nExporting merged tables to parquet ...")
    RESTRUCTURED_PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    rst_pq_dir = RESTRUCTURED_PARQUET_DIR / "merged"
    rst_pq_dir.mkdir(parents=True, exist_ok=True)

    for name, fqn in rtbl.items():
        schema_name, table_name = fqn.split(".")
        pq_path = rst_pq_dir / f"{schema_name}_{table_name}.parquet"
        abs_path = pq_path.resolve()
        con.execute(f"COPY {fqn} TO '{abs_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        con.execute(f"DROP TABLE {fqn}")
        con.execute(f"CREATE VIEW {fqn} AS SELECT * FROM read_parquet('{abs_path}')")
        size_mb = pq_path.stat().st_size / 1e6
        print(f"  {fqn} → {pq_path.name} ({size_mb:.0f} MB)")

    con.execute("CHECKPOINT")
    con.close()
    size_gb = dest.stat().st_size / 1e9
    print(f"\nRestructured DB created: {dest} ({size_gb:.2f} GB)")
    return dest


# ── SQL Transformation ─────────────────────────────────────────────────────


def transform_sql_to_obfuscated(sql: str, dictionary: dict) -> str:
    """Apply dictionary renaming to a SQL query.

    Replaces schema.table references and column names.
    Output column aliases (AS sofa, AS respiration, etc.) are preserved
    since they appear after AS and don't match bare column references.
    """
    result = sql

    # 1. Replace fully-qualified table references (schema.table)
    # Sort by length descending to avoid partial matches
    table_replacements = sorted(
        dictionary["tables"].items(), key=lambda x: len(x[0]), reverse=True
    )
    for native_fqn, obf_fqn in table_replacements:
        # Match schema.table as whole words
        pattern = re.compile(re.escape(native_fqn) + r"(?![.\w])")
        result = pattern.sub(obf_fqn, result)

    # 2. Replace bare table names (without schema prefix)
    # Extract bare table names from FQN mappings
    bare_table_map = {}
    for native_fqn, obf_fqn in dictionary["tables"].items():
        _, bare_table = native_fqn.split(".")
        obf_bare = obf_fqn.split(".")[1]
        bare_table_map[bare_table] = obf_bare

    # 3. Replace column names — only when they appear as SQL identifiers
    # Sort by length descending to prevent partial matches
    col_replacements = sorted(
        dictionary["columns"].items(), key=lambda x: len(x[0]), reverse=True
    )
    for native_col, obf_col in col_replacements:
        # Match column name as an identifier boundary.
        # Allow . before (table.column syntax) but not other word chars.
        # Lookahead: not followed by word chars.
        pattern = re.compile(r"(?<!\w)" + re.escape(native_col) + r"(?!\w)")
        result = pattern.sub(obf_col, result)

    return result


def generate_obfuscated_gt_sql(dictionary: dict | None = None) -> None:
    """Generate obfuscated ground truth SQL for all tasks."""
    if dictionary is None:
        dictionary = load_dictionary()

    out_dir = GROUND_TRUTH_DIR / "obfuscated"
    out_dir.mkdir(parents=True, exist_ok=True)

    task_keys = set(_mimic_ground_truth_task_keys())
    for sql_file in sorted(GROUND_TRUTH_DIR.glob("*.sql")):
        if sql_file.stem not in task_keys:
            continue
        native_sql = sql_file.read_text()
        obf_sql = transform_sql_to_obfuscated(native_sql, dictionary)
        out_path = out_dir / sql_file.name
        out_path.write_text(obf_sql)
        print(f"  {sql_file.name} → {out_path}")


def _mimic_ground_truth_task_keys() -> list[str]:
    """Return ground-truth SQL keys used by MIMIC-IV benchmark tasks."""
    from .db import _task_key, list_task_dirs, load_task_config

    keys: set[str] = set()
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        if config.get("database", {}).get("source", "mimic-iv") != "mimic-iv":
            continue
        name = config["metadata"]["name"]
        keys.add(config.get("ground_truth", {}).get("alias", _task_key(name)))
    return sorted(keys)


def generate_restructured_gt_sql(dictionary: dict | None = None) -> None:
    """Validate that manually authored restructured ground-truth SQL is present.

    Restructured schemas merge and split source tables, so preserving query
    semantics requires hand-authored SQL plus differential verification against
    native and obfuscated outputs. This setup hook intentionally does not
    rewrite SQL and does not run the expensive equivalence suite; use
    `setup.py --verify-equivalence` or `python -m benchmark.lib.transform verify`
    for differential verification.
    """
    if dictionary is None:
        dictionary = load_dictionary()

    missing = [
        task_key
        for task_key in _mimic_ground_truth_task_keys()
        if not (GROUND_TRUTH_DIR / "restructured" / f"{task_key}.sql").exists()
    ]
    if missing:
        raise FileNotFoundError(
            "missing manually authored restructured ground-truth SQL for: "
            + ", ".join(missing)
        )

    for task_key in _mimic_ground_truth_task_keys():
        out_path = GROUND_TRUTH_DIR / "restructured" / f"{task_key}.sql"
        print(f"  {task_key}.sql ready at {out_path}")


def _generate_restructured_gt_sql_unsafe(dictionary: dict | None = None) -> None:
    """Legacy best-effort generator retained only for manual migration work."""
    if dictionary is None:
        dictionary = load_dictionary()

    obf_dir = GROUND_TRUTH_DIR / "obfuscated"
    out_dir = GROUND_TRUTH_DIR / "restructured"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not obf_dir.exists():
        raise FileNotFoundError(
            f"Obfuscated GT SQL not found at {obf_dir}. "
            "Run generate_obfuscated_gt_sql() first."
        )

    for sql_file in sorted(obf_dir.glob("*.sql")):
        obf_sql = sql_file.read_text()
        rst_sql = _apply_structural_rewrites(obf_sql, dictionary)
        out_path = out_dir / sql_file.name
        out_path.write_text(rst_sql)
        print(f"  {sql_file.name} → {out_path}")


def _build_structural_replacements(dictionary: dict) -> dict:
    """Build regex patterns for structural table replacements."""
    tbl = dictionary["tables"]
    rtbl = dictionary["restructured_tables"]
    rcol = dictionary["restructured_columns"]

    return {
        "chartevents": {
            "from": tbl["mimiciv_icu.chartevents"],
            "to": rtbl["observations"],
            "filter_col": rcol["source"],
            "filter_val": "chart",
        },
        "labevents": {
            "from": tbl["mimiciv_hosp.labevents"],
            "to": rtbl["observations"],
            "filter_col": rcol["source"],
            "filter_val": "lab",
        },
        "inputevents": {
            "from": tbl["mimiciv_icu.inputevents"],
            "to": rtbl["flows"],
            "filter_col": rcol["direction"],
            "filter_val": "in",
        },
        "outputevents": {
            "from": tbl["mimiciv_icu.outputevents"],
            "to": rtbl["flows"],
            "filter_col": rcol["direction"],
            "filter_val": "out",
        },
        "patients": {
            "from": tbl["mimiciv_hosp.patients"],
            "to": rtbl["encounters"],
            "filter_col": None,
            "filter_val": None,
        },
        "admissions": {
            "from": tbl["mimiciv_hosp.admissions"],
            "to": rtbl["encounters"],
            "filter_col": None,
            "filter_val": None,
        },
        "icustays": {
            "from": tbl["mimiciv_icu.icustays"],
            "to": rtbl["encounters"],
            "filter_col": None,
            "filter_val": None,
        },
        "d_items": {
            "from": tbl["mimiciv_icu.d_items"],
            "to": rtbl["item_reference"],
            "filter_col": rcol["item_type"],
            "filter_val": "chart",
        },
        "d_labitems": {
            "from": tbl["mimiciv_hosp.d_labitems"],
            "to": rtbl["item_reference"],
            "filter_col": rcol["item_type"],
            "filter_val": "lab",
        },
    }


def _apply_structural_rewrites(sql: str, dictionary: dict) -> str:
    """Apply legacy structural table replacements to obfuscated SQL.

    This helper is intentionally not used by the public generator because it
    does not preserve discriminator filters or merged-table join semantics.
    """
    replacements = _build_structural_replacements(dictionary)
    result = sql

    # Replace table references in FROM/JOIN clauses
    # For merged tables with discriminators, add WHERE filter
    for name, repl in replacements.items():
        old_tbl = repl["from"]
        new_tbl = repl["to"]

        if old_tbl not in result:
            continue

        # Simple replacement: just swap the table name
        # The discriminator filter needs manual addition for complex queries
        result = result.replace(old_tbl, new_tbl)

    # Add comments marking where manual review is needed
    if rtbl_ref := dictionary["restructured_tables"]["encounters"]:
        if rtbl_ref in result:
            # The encounters merge eliminates JOIN clauses — flag for review
            result = (
                f"-- NOTE: This SQL references the encounters table ({rtbl_ref}).\n"
                f"-- The patients+admissions+icustays JOIN pattern has been replaced.\n"
                f"-- Manual review required to remove redundant JOINs.\n\n" + result
            )

    return result


# ── Instruction Generation ─────────────────────────────────────────────────


def generate_obfuscated_instruction(
    native_instruction: str,
    dictionary: dict,
    include_restructured_tables: bool = False,
) -> str:
    """Transform a native task instruction for the obfuscated/restructured schema.

    Replaces MIMIC-specific names and appends a dictionary section.
    Clinical scoring definitions are preserved unchanged.
    """
    result = native_instruction

    # Replace "MIMIC-IV" with neutral term
    result = result.replace("a MIMIC-IV clinical", "a clinical")
    result = result.replace("A MIMIC-IV clinical", "A clinical")
    result = result.replace("MIMIC-IV", "")
    result = result.replace("mimic-iv", "")

    # Replace schema names in backticks
    for native_schema, obf_schema in dictionary["schemas"].items():
        result = result.replace(f"`{native_schema}`", f"`{obf_schema}`")
        result = result.replace(native_schema, obf_schema)

    # Replace table names mentioned in instructions
    # Only replace well-known base table names that appear in instructions
    instruction_tables = {
        "chartevents": dictionary["tables"]["mimiciv_icu.chartevents"],
        "labevents": dictionary["tables"]["mimiciv_hosp.labevents"],
        "inputevents": dictionary["tables"]["mimiciv_icu.inputevents"],
        "outputevents": dictionary["tables"]["mimiciv_icu.outputevents"],
        "procedureevents": dictionary["tables"]["mimiciv_icu.procedureevents"],
        "d_items": dictionary["tables"]["mimiciv_icu.d_items"],
    }
    for native_name, obf_fqn in instruction_tables.items():
        obf_bare = obf_fqn.split(".")[1]
        result = result.replace(f"`{native_name}`", f"`{obf_bare}`")

    # Append dictionary section
    result += _format_dictionary_section(dictionary, include_restructured_tables)

    return result


def _format_dictionary_section(
    dictionary: dict, include_restructured: bool = False
) -> str:
    """Format the dictionary as a markdown section for task instructions."""
    col = dictionary["columns"]
    tbl = dictionary["tables"]
    schema = dictionary["schemas"]

    lines = [
        "\n\n---\n",
        "## Schema Dictionary\n",
        (
            "This database uses renamed schema objects with a semantic map. "
            "Use this reference to navigate.\n"
            if include_restructured
            else "This database uses obfuscated names. Use this reference to navigate.\n"
        ),
        "### Schemas",
        "| Description | Database name |",
        "|-------------|---------------|",
    ]
    for native, obf in sorted(schema.items()):
        desc = _SCHEMA_DESCRIPTIONS.get(native, "database schema")
        lines.append(f"| {desc} | `{obf}` |")

    lines.extend(
        [
            "\n### Key Tables",
            "| Description | Database name |",
            "|-------------|---------------|",
        ]
    )
    for fqn, desc in _TABLE_DESCRIPTIONS.items():
        if fqn in tbl:
            lines.append(f"| {desc} | `{tbl[fqn]}` |")

    if include_restructured:
        rtbl = dictionary["restructured_tables"]
        rcol = dictionary["restructured_columns"]
        lines.extend(
            [
                "\n### Restructured Tables",
                "| Description | Database name | Discriminator |",
                "|-------------|---------------|---------------|",
                f"| combined clinical observations | `{rtbl['observations']}` | `{rcol['source']}`: 'chart' or 'lab' |",
                f"| patient encounter records | `{rtbl['encounters']}` | Single table, one row per admission/stay |",
                f"| clinical substance flows | `{rtbl['flows']}` | `{rcol['direction']}`: 'in' or 'out' |",
                f"| measurement reference dictionary | `{rtbl['item_reference']}` | `{rcol['item_type']}`: 'chart' or 'lab' |",
                "",
                "**Note**: The original separate tables listed above do NOT exist.",
                "Use the restructured tables instead. Explore their columns with",
                "`DESCRIBE table_name` or `PRAGMA table_info('schema.table')`.",
            ]
        )

    # Key columns
    key_columns = [
        "subject_id",
        "hadm_id",
        "stay_id",
        "itemid",
        "charttime",
        "starttime",
        "endtime",
        "storetime",
        "value",
        "valuenum",
        "valueuom",
        "intime",
        "outtime",
        "admittime",
        "dischtime",
        "label",
        "category",
        "gender",
        "anchor_age",
        "los",
        "admission_type",
        "hospital_expire_flag",
        "icd_code",
        "icd_version",
        "rate",
        "rateuom",
        "amount",
        "amountuom",
        "patientweight",
        "curr_service",
        "seq_num",
        "flag",
        "specimen_id",
        "labevent_id",
        "caregiver_id",
        "warning",
        "ref_range_lower",
        "ref_range_upper",
        "abbreviation",
        "linksto",
        "unitname",
        "param_type",
        "fluid",
        "dod",
        "deathtime",
        "first_careunit",
        "last_careunit",
    ]

    lines.extend(
        [
            "\n### Key Columns",
            "| Description | Database name |",
            "|-------------|---------------|",
        ]
    )
    for native_col in key_columns:
        if native_col in col:
            desc = _COLUMN_DESCRIPTIONS.get(native_col, "database column")
            lines.append(f"| {desc} | `{col[native_col]}` |")

    if include_restructured:
        rcol = dictionary["restructured_columns"]
        lines.extend(
            [
                f"| observation source discriminator | `{rcol['source']}` |",
                f"| flow direction discriminator | `{rcol['direction']}` |",
                f"| item type discriminator | `{rcol['item_type']}` |",
            ]
        )

    lines.append("")
    return "\n".join(lines)


# ── Per-Task Agent DB Setup ────────────────────────────────────────────────


def setup_transformed_agent_db(
    task_dir: Path,
    schema_type: str,
    dictionary: dict | None = None,
) -> Path:
    """Create an obfuscated or restructured agent DB for a task.

    Copies the transformed source DB and drops the mapped table names
    from the task's drop_tables list.
    """
    from .db import _remove_wal, compact_duckdb_file, load_task_config

    if dictionary is None:
        dictionary = load_dictionary()

    config = load_task_config(task_dir)
    task_name = config["metadata"]["name"]
    task_key = task_name.replace("mimic-", "")
    drop_tables = list(config.get("database", {}).get("drop_tables", []))

    if schema_type == "obfuscated":
        source_db = OBFUSCATED_DB
    elif schema_type == "restructured":
        source_db = RESTRUCTURED_DB
    else:
        raise ValueError(f"Unknown schema_type: {schema_type}")

    if not source_db.exists():
        raise FileNotFoundError(
            f"Source DB not found: {source_db}. Run create_{schema_type}_db() first."
        )

    AGENT_DB_DIR.mkdir(parents=True, exist_ok=True)
    dest = AGENT_DB_DIR / f"{schema_type}_{task_key}.duckdb"

    print(f"Copying {source_db} → {dest} ...")
    _remove_wal(dest)
    shutil.copy2(source_db, dest)
    wal = source_db.with_suffix(".duckdb.wal")
    if wal.exists():
        shutil.copy2(wal, dest.with_suffix(".duckdb.wal"))
    else:
        _remove_wal(dest)

    # Map native drop_tables to obfuscated/restructured names. Raw MIMIC tasks
    # remove the whole transformed derived schema so shortcut exposure cannot
    # depend on task wording or incomplete task-local drop lists.
    con = duckdb.connect(str(dest))

    if config.get("metadata", {}).get("mode") == "raw":
        derived_schema = dictionary["schemas"].get("mimiciv_derived")
        if derived_schema:
            derived_relations = con.execute(
                """
                SELECT table_schema || '.' || table_name
                FROM information_schema.tables
                WHERE table_schema = ?
                ORDER BY table_name
                """,
                [derived_schema],
            ).fetchall()
            for (relation,) in derived_relations:
                _drop_table_or_view(con, relation)
                print(f"  Dropped {relation} (raw derived schema)")

    dropped = []
    for native_table in drop_tables:
        # Try obfuscated table name first
        if native_table in dictionary["tables"]:
            obf_table = dictionary["tables"][native_table]
            # For restructured, the table may have been merged into another
            # Check if it still exists
            exists = con.execute(
                f"SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema || '.' || table_name = '{obf_table}'"
            ).fetchone()[0]
            if exists:
                _drop_table_or_view(con, obf_table)
                dropped.append((native_table, obf_table))
                print(f"  Dropped {obf_table} (was {native_table})")
            else:
                print(
                    f"  Skipped {native_table} → {obf_table} (already merged/removed)"
                )
        else:
            print(f"  WARNING: {native_table} not in dictionary")

    failures = []
    for native_table, obf_table in dropped:
        still_present = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema || '.' || table_name = '{obf_table}'"
        ).fetchone()[0]
        if still_present:
            failures.append(f"{obf_table} (was {native_table})")
    if failures:
        con.close()
        raise RuntimeError(
            f"{schema_type}/{task_key}: transformed DB still contains dropped "
            f"relations: {', '.join(failures)}"
        )

    con.close()
    if drop_tables:
        print("  Compacting agent DB ...")
        compact_duckdb_file(dest)
    print(f"Agent DB ready at {dest}")
    return dest


# ── Verification ───────────────────────────────────────────────────────────


def verify_dictionary_completeness(
    db_path: Path = SOURCE_DB,
    dictionary: dict | None = None,
) -> bool:
    """Verify every schema/table/column in the DB has a dictionary entry."""
    if dictionary is None:
        dictionary = load_dictionary()

    con = duckdb.connect(str(db_path), read_only=True)
    ok = True

    # Check schemas
    schemas = {
        row[0]
        for row in con.execute(
            "SELECT DISTINCT table_schema FROM information_schema.columns"
        ).fetchall()
        if row[0] not in SKIP_SCHEMAS
    }
    for schema in schemas:
        if schema not in dictionary["schemas"]:
            print(f"  MISSING schema: {schema}")
            ok = False

    # Check tables
    tables = con.execute(
        "SELECT DISTINCT table_schema, table_name FROM information_schema.columns "
        "WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'main')"
    ).fetchall()
    for schema, table in tables:
        fqn = f"{schema}.{table}"
        if fqn not in dictionary["tables"]:
            print(f"  MISSING table: {fqn}")
            ok = False

    # Check columns
    columns = con.execute(
        "SELECT DISTINCT column_name FROM information_schema.columns "
        "WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'main')"
    ).fetchall()
    for (col,) in columns:
        if col not in dictionary["columns"]:
            print(f"  MISSING column: {col}")
            ok = False

    con.close()
    if ok:
        print("Dictionary completeness: OK")
    return ok


def verify_gt_equivalence(
    task_key: str,
    dictionary: dict | None = None,
) -> bool:
    """Verify that native, obfuscated, and restructured GT produce identical output."""
    if dictionary is None:
        dictionary = load_dictionary()

    import pandas as pd

    from .db import _task_key, list_task_dirs, load_task_config

    native_sql = (GROUND_TRUTH_DIR / f"{task_key}.sql").read_text()
    obf_sql_path = GROUND_TRUTH_DIR / "obfuscated" / f"{task_key}.sql"
    rst_sql_path = GROUND_TRUTH_DIR / "restructured" / f"{task_key}.sql"
    missing_sql = [
        str(path.relative_to(GROUND_TRUTH_DIR))
        for path in (obf_sql_path, rst_sql_path)
        if not path.exists()
    ]
    if missing_sql:
        print(f"  {task_key}: missing transformed GT SQL: {', '.join(missing_sql)}")
        return False

    key_columns: list[str] = []
    for task_dir in list_task_dirs():
        config = load_task_config(task_dir)
        if config.get("database", {}).get("source", "mimic-iv") != "mimic-iv":
            continue
        name = config["metadata"]["name"]
        gt_key = config.get("ground_truth", {}).get("alias", _task_key(name))
        if gt_key == task_key:
            key_columns = config["evaluation"]["key_columns"]
            break

    # Run native
    con_native = duckdb.connect(str(SOURCE_DB), read_only=True)
    df_native = con_native.execute(native_sql).df()
    con_native.close()

    ok = True

    def _sort_columns(
        df, native_df, native_columns: list[str], transformed: bool
    ) -> list[str]:
        mapped_columns = [
            dictionary["columns"].get(col, col) if transformed else col
            for col in native_columns
        ]
        if all(col in df.columns for col in mapped_columns):
            return mapped_columns
        fallback = []
        for col in native_columns:
            if col in native_df.columns:
                idx = list(native_df.columns).index(col)
                if idx < len(df.columns):
                    fallback.append(df.columns[idx])
        return fallback or list(df.columns[:3])

    def _compare_dfs(df_a, df_b, label: str) -> bool:
        """Compare two DataFrames by sorting on configured task key columns."""
        if df_a.shape != df_b.shape:
            print(f"  {task_key} {label}: SHAPE MISMATCH {df_a.shape} vs {df_b.shape}")
            return False

        sort_keys = key_columns or list(df_a.columns[:3])
        sort_cols_a = _sort_columns(df_a, df_a, sort_keys, transformed=False)
        sort_cols_b = _sort_columns(df_b, df_a, sort_keys, transformed=True)
        df_a = df_a.sort_values(sort_cols_a).reset_index(drop=True)
        df_b = df_b.sort_values(sort_cols_b).reset_index(drop=True)

        col_ok = True
        for i, (ca, cb) in enumerate(zip(df_a.columns, df_b.columns)):
            a_vals = df_a[ca].values
            b_vals = df_b[cb].values
            mismatches = sum(
                1
                for j in range(len(a_vals))
                if not (pd.isna(a_vals[j]) and pd.isna(b_vals[j]))
                and a_vals[j] != b_vals[j]
            )
            if mismatches > 0:
                print(f"  {task_key} {label} col {ca}: {mismatches} mismatches")
                col_ok = False

        if col_ok:
            print(f"  {task_key} {label}: OK ({len(df_a)} rows)")
        return col_ok

    # Run obfuscated
    obf_sql = obf_sql_path.read_text()
    con_obf = duckdb.connect(str(OBFUSCATED_DB), read_only=True)
    try:
        df_obf = con_obf.execute(obf_sql).df()
        if not _compare_dfs(df_native, df_obf, "obfuscated"):
            ok = False
    except Exception as e:
        print(f"  {task_key} obfuscated: ERROR — {e}")
        ok = False
    finally:
        con_obf.close()

    # Run restructured
    rst_sql = rst_sql_path.read_text()
    con_rst = duckdb.connect(str(RESTRUCTURED_DB), read_only=True)
    try:
        df_rst = con_rst.execute(rst_sql).df()
        if not _compare_dfs(df_native, df_rst, "restructured"):
            ok = False
    except Exception as e:
        print(f"  {task_key} restructured: ERROR — {e}")
        ok = False
    finally:
        con_rst.close()

    return ok


# ── Helper functions ───────────────────────────────────────────────────────


def _drop_table_or_view(con: duckdb.DuckDBPyConnection, fqn: str) -> None:
    """Drop a table or view by name, auto-detecting the type."""
    try:
        con.execute(f"DROP TABLE IF EXISTS {fqn}")
    except duckdb.CatalogException:
        con.execute(f"DROP VIEW IF EXISTS {fqn}")


def _get_column_names(con: duckdb.DuckDBPyConnection, fqn: str) -> list[str]:
    """Get column names for a table in order."""
    rows = con.execute(f"PRAGMA table_info('{fqn}')").fetchall()
    return [row[1] for row in rows]


def _get_column_type(con: duckdb.DuckDBPyConnection, fqn: str, col_name: str) -> str:
    """Get the SQL type of a column."""
    rows = con.execute(f"PRAGMA table_info('{fqn}')").fetchall()
    for row in rows:
        if row[1] == col_name:
            return row[2]
    raise KeyError(f"Column '{col_name}' not found in {fqn}")


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MIMIC-IV contamination analysis: schema transformations"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("build-dictionary", help="Generate renaming dictionary")
    sub.add_parser("create-obfuscated", help="Create obfuscated database")
    sub.add_parser("create-restructured", help="Create restructured database")
    sub.add_parser("generate-gt", help="Generate transformed ground truth SQL")
    sub.add_parser("verify", help="Verify transformations")

    args = parser.parse_args()

    if args.command == "build-dictionary":
        d = build_dictionary()
        save_dictionary(d)
        verify_dictionary_completeness(dictionary=d)

    elif args.command == "create-obfuscated":
        d = load_dictionary()
        create_obfuscated_db(dictionary=d)

    elif args.command == "create-restructured":
        d = load_dictionary()
        create_restructured_db(dictionary=d)

    elif args.command == "generate-gt":
        d = load_dictionary()
        print("Generating obfuscated GT SQL ...")
        generate_obfuscated_gt_sql(d)
        print("\nSkipping restructured GT SQL generation.")
        print(
            "Restructured ground-truth SQL must be authored manually and "
            "verified with `verify`."
        )

    elif args.command == "verify":
        d = load_dictionary()
        print("Verifying dictionary completeness ...")
        ok = verify_dictionary_completeness(dictionary=d)
        print("\nVerifying GT equivalence for MIMIC-IV task ground truth ...")
        for task_key in _mimic_ground_truth_task_keys():
            ok = verify_gt_equivalence(task_key, dictionary=d) and ok
        raise SystemExit(0 if ok else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
