"""Dataset definitions with modality-based filtering.

This module provides:
- Modality enum: Data types available in a dataset (TABULAR, NOTES, etc.)
- DatasetDefinition: Dataset metadata with modalities
- DatasetRegistry: Registry for managing dataset definitions
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from m4.core.exceptions import DatasetError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Maximum file size for custom dataset JSON files (1MB)
# Prevents memory exhaustion from malicious/oversized files
MAX_DATASET_FILE_SIZE = 1024 * 1024


class Modality(Enum):
    """Data modalities available in a dataset.

    Modalities describe what kinds of data a dataset contains. Tools declare
    which modalities they require, and only datasets with those modalities
    will have the tool available.

    This is intentionally high-level. Fine-grained data discovery (which tables
    exist, what columns they have) is handled by schema introspection tools
    and the LLM's ability to write adaptive SQL.
    """

    TABULAR = auto()  # Structured tables (labs, demographics, vitals, etc.)
    NOTES = auto()  # Clinical notes and discharge summaries


@dataclass
class DatasetDefinition:
    """Dataset definition with modality declarations.

    Attributes:
        name: Unique identifier for the dataset
        description: Human-readable description
        version: The PhysioNet version M4 downloads (matching file_listing_url),
            or None when not known
        file_listing_url: URL for downloading dataset files
        subdirectories_to_scan: Directories to scan for data files
        default_duckdb_filename: Default filename for local DuckDB database
        primary_verification_table: Table to check for dataset verification
        bigquery_project_id: Google Cloud project ID for BigQuery access
        bigquery_dataset_ids: BigQuery dataset IDs containing the tables
        requires_authentication: Whether dataset requires auth (e.g., credentialed access)
        modalities: Immutable set of data modalities (TABULAR, NOTES, etc.)
        related_datasets: Cross-references to related datasets with linkage info
        title: Short display name; the dataset name when not given
        summary: One or two plain sentences on what the dataset holds, for a
            researcher deciding whether to download it
        download_size_gb: Approximate size in GB (1024^3 bytes) of the raw
            .csv.gz files M4 downloads, or None when not known
    """

    name: str
    description: str = ""
    version: str | None = None
    file_listing_url: str | None = None
    subdirectories_to_scan: list[str] = field(default_factory=list)
    default_duckdb_filename: str | None = None
    primary_verification_table: str | None = None

    # BigQuery Configuration
    bigquery_project_id: str | None = "physionet-data"
    bigquery_dataset_ids: list[str] = field(default_factory=list)

    # Authentication
    requires_authentication: bool = False

    # Modality declarations (immutable)
    modalities: frozenset[Modality] = field(default_factory=frozenset)

    # Related datasets (for cross-referencing, e.g., notes linked via subject_id)
    # Format: {"dataset-name": "Description of how to link"}
    related_datasets: dict[str, str] = field(default_factory=dict)

    # Access and local layout guidance. These fields are metadata only; M4 does
    # not collect credentialed dataset passwords.
    dataset_page_url: str | None = None
    dua_url: str | None = None
    bigquery_access_url: str | None = None
    expected_raw_subdirectories: list[str] = field(default_factory=list)
    recommended_local_target_root: str | None = None

    # Filesystem directory -> canonical schema name
    # e.g. {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"}
    # Root-level files use empty string key: {"": "eicu_crd"}
    schema_mapping: dict[str, str] = field(default_factory=dict)

    # Canonical schema -> BigQuery dataset ID
    # e.g. {"mimiciv_hosp": "mimiciv_hosp"}
    bigquery_schema_mapping: dict[str, str] = field(default_factory=dict)

    # Catalog metadata, shown to people choosing a dataset (`m4 list-datasets`)
    title: str | None = None
    summary: str | None = None
    download_size_gb: float | None = None

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.default_duckdb_filename:
            self.default_duckdb_filename = f"{self.name.replace('-', '_')}.duckdb"
        if not self.title:
            self.title = self.name


class DatasetRegistry:
    """Registry for managing dataset definitions.

    This class maintains a global registry of available datasets with
    enhanced capability metadata.
    """

    _registry: ClassVar[dict[str, DatasetDefinition]] = {}
    # The datasets that ship with M4. A file in the custom datasets folder
    # cannot redefine one: wrappers and their users rely on these names meaning
    # the definitions below, download address included.
    _builtin_names: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def register(cls, dataset: DatasetDefinition):
        """Register a dataset in the registry.

        Args:
            dataset: DatasetDefinition to register
        """
        cls._registry[dataset.name.lower()] = dataset

    @classmethod
    def get(cls, name: str) -> DatasetDefinition | None:
        """Get a dataset by name.

        Args:
            name: Dataset name (case-insensitive)

        Returns:
            DatasetDefinition if found, None otherwise
        """
        return cls._registry.get(name.lower())

    @classmethod
    def list_all(cls) -> list[DatasetDefinition]:
        """Get all registered datasets.

        Returns:
            List of all DatasetDefinition objects
        """
        return list(cls._registry.values())

    @classmethod
    def is_builtin(cls, name: str) -> bool:
        """Whether `name` (case-insensitive) is one of the datasets M4 ships."""
        return name.lower() in cls._builtin_names

    @classmethod
    def get_active(cls) -> DatasetDefinition:
        """Deprecated compatibility shim for removed global dataset state."""
        raise DatasetError(
            "DatasetRegistry.get_active() is no longer supported because M4 no "
            "longer keeps a global active dataset. Resolve datasets explicitly "
            "with DatasetRegistry.get(name) or M4Client(dataset=name)."
        )

    @classmethod
    def reset(cls):
        """Clear registry and re-register built-in datasets."""
        cls._registry.clear()
        cls._register_builtins()

    @classmethod
    def load_custom_datasets(cls, custom_dir: Path) -> None:
        """Load custom dataset definitions from JSON files.

        JSON files can specify modalities as string arrays:
            "modalities": ["TABULAR", "NOTES"]

        If not specified, defaults to TABULAR modality.

        Args:
            custom_dir: Directory containing custom dataset JSON files
        """
        if not custom_dir.exists():
            logger.debug(f"Custom datasets directory does not exist: {custom_dir}")
            return

        for f in custom_dir.glob("*.json"):
            try:
                # Check file size to prevent DoS via large files
                if f.stat().st_size > MAX_DATASET_FILE_SIZE:
                    logger.warning(
                        f"Dataset file too large (>{MAX_DATASET_FILE_SIZE} bytes), "
                        f"skipping: {f}"
                    )
                    continue

                data = json.loads(f.read_text())

                if str(data.get("name", "")).lower() in cls._builtin_names:
                    logger.warning(
                        f"Ignoring custom dataset file {f}: '{data['name']}' is a "
                        "built-in dataset, and a file cannot redefine one."
                    )
                    continue

                # Convert string arrays to enum frozensets
                if "modalities" in data:
                    data["modalities"] = frozenset(
                        Modality[m] for m in data["modalities"]
                    )
                else:
                    # Default: tabular data
                    data["modalities"] = frozenset({Modality.TABULAR})

                # Default empty dicts for schema mapping fields
                data.setdefault("schema_mapping", {})
                data.setdefault("bigquery_schema_mapping", {})

                ds = DatasetDefinition(**data)
                cls.register(ds)
                logger.debug(f"Loaded custom dataset: {ds.name}")
            except KeyError as e:
                logger.warning(
                    f"Failed to load custom dataset from {f}: "
                    f"Invalid modality name: {e}"
                )
            except Exception as e:
                logger.warning(f"Failed to load custom dataset from {f}: {e}")

    @classmethod
    def _register_builtins(cls):
        """Register built-in datasets."""
        # Versions, summaries and sizes follow each dataset's PhysioNet page.
        # download_size_gb sums the .csv.gz files M4 downloads; PhysioNet shows
        # file sizes of a credentialed dataset only to people with access, so
        # those are None rather than a guess.
        mimic_iv_demo = DatasetDefinition(
            name="mimic-iv-demo",
            title="MIMIC-IV demo",
            description="MIMIC-IV Clinical Database Demo",
            summary=(
                "Open sample of MIMIC-IV: the hospital and ICU tables for 100 "
                "patients of Beth Israel Deaconess Medical Center in Boston, "
                "without free-text notes. For trying M4 and checking whether "
                "MIMIC-IV fits a study before requesting access."
            ),
            version="2.2",
            download_size_gb=0.015,
            dataset_page_url="https://physionet.org/content/mimic-iv-demo/",
            file_listing_url="https://physionet.org/files/mimic-iv-demo/2.2/",
            subdirectories_to_scan=["hosp", "icu"],
            expected_raw_subdirectories=["hosp", "icu"],
            recommended_local_target_root="m4_data/raw_files/mimic-iv-demo",
            primary_verification_table="mimiciv_hosp.admissions",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
            modalities=frozenset({Modality.TABULAR}),
            related_datasets={
                "mimic-iv-ed-demo": (
                    "Emergency department stays of the same 100 patients. "
                    "Link via subject_id."
                ),
            },
            schema_mapping={"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"},
        )

        mimic_iv = DatasetDefinition(
            name="mimic-iv",
            title="MIMIC-IV",
            description="MIMIC-IV Clinical Database",
            summary=(
                "Hospital and ICU records of patients admitted to the emergency "
                "department or an ICU at Beth Israel Deaconess Medical Center in "
                "Boston, 2008-2022. About 365,000 patients, 546,000 "
                "hospitalizations and 94,000 ICU stays."
            ),
            version="3.1",
            dataset_page_url="https://physionet.org/content/mimiciv/",
            dua_url="https://physionet.org/content/mimiciv/",
            bigquery_access_url="https://physionet.org/content/mimiciv/view-required-training/3.1/",
            file_listing_url="https://physionet.org/files/mimiciv/3.1/",
            subdirectories_to_scan=["hosp", "icu"],
            expected_raw_subdirectories=["hosp", "icu"],
            recommended_local_target_root="m4_data/raw_files/mimic-iv",
            primary_verification_table="mimiciv_hosp.admissions",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=[
                "mimiciv_3_1_hosp",
                "mimiciv_3_1_icu",
                "mimiciv_derived",
            ],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            related_datasets={
                "mimic-iv-note": (
                    "Clinical notes (discharge summaries, radiology reports). "
                    "Link via subject_id."
                ),
                "mimic-iv-ed": (
                    "Emergency department stays (triage, vitals, medications, "
                    "diagnoses). Link via subject_id, or hadm_id for stays that "
                    "led to a hospital admission."
                ),
            },
            schema_mapping={
                "hosp": "mimiciv_hosp",
                "icu": "mimiciv_icu",
                "derived": "mimiciv_derived",
            },
            bigquery_schema_mapping={
                "mimiciv_hosp": "mimiciv_3_1_hosp",
                "mimiciv_icu": "mimiciv_3_1_icu",
                "mimiciv_derived": "mimiciv_derived",
            },
        )

        mimic_iv_note = DatasetDefinition(
            name="mimic-iv-note",
            title="MIMIC-IV-Note",
            description="MIMIC-IV Clinical Notes (discharge summaries, radiology reports)",
            summary=(
                "Free-text notes of MIMIC-IV patients at Beth Israel Deaconess "
                "Medical Center: 331,794 discharge summaries for 145,915 patients "
                "and 2,321,355 radiology reports for 237,427 patients. Links to "
                "MIMIC-IV via subject_id."
            ),
            version="2.2",
            dataset_page_url="https://physionet.org/content/mimic-iv-note/",
            dua_url="https://physionet.org/content/mimic-iv-note/",
            bigquery_access_url="https://physionet.org/content/mimic-iv-note/view-required-training/2.2/",
            file_listing_url="https://physionet.org/files/mimic-iv-note/2.2/",
            subdirectories_to_scan=["note"],
            expected_raw_subdirectories=["note"],
            recommended_local_target_root="m4_data/raw_files/mimic-iv-note",
            primary_verification_table="mimiciv_note.discharge",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_note"],
            requires_authentication=True,
            modalities=frozenset({Modality.NOTES}),
            related_datasets={
                "mimic-iv": (
                    "Structured clinical data (labs, vitals, admissions). "
                    "Link via subject_id."
                ),
            },
            schema_mapping={"note": "mimiciv_note"},
            bigquery_schema_mapping={"mimiciv_note": "mimiciv_note"},
        )

        mimic_iv_ed_demo = DatasetDefinition(
            name="mimic-iv-ed-demo",
            title="MIMIC-IV-ED demo",
            description="MIMIC-IV-ED Demo",
            summary=(
                "Open sample of MIMIC-IV-ED: all of its emergency department "
                "tables for 100 patients, the same patients as the MIMIC-IV demo. "
                "For trying ED queries before requesting access."
            ),
            version="2.2",
            download_size_gb=0.000082,
            dataset_page_url="https://physionet.org/content/mimic-iv-ed-demo/",
            file_listing_url="https://physionet.org/files/mimic-iv-ed-demo/2.2/",
            subdirectories_to_scan=["ed"],
            expected_raw_subdirectories=["ed"],
            recommended_local_target_root="m4_data/raw_files/mimic-iv-ed-demo",
            primary_verification_table="mimiciv_ed.edstays",
            # The demo lives in PhysioNet's public demo project, not physionet-data
            bigquery_project_id="physionet-demo",
            bigquery_dataset_ids=["mimiciv_ed"],
            modalities=frozenset({Modality.TABULAR}),
            related_datasets={
                "mimic-iv-demo": (
                    "Hospital and ICU data of the same 100 patients. "
                    "Link via subject_id."
                ),
            },
            schema_mapping={"ed": "mimiciv_ed"},
            bigquery_schema_mapping={"mimiciv_ed": "mimiciv_ed"},
        )

        mimic_iv_ed = DatasetDefinition(
            name="mimic-iv-ed",
            title="MIMIC-IV-ED",
            description="MIMIC-IV Emergency Department Module",
            summary=(
                "Emergency department stays at Beth Israel Deaconess Medical "
                "Center in Boston, 2011-2019: about 425,000 stays with triage, "
                "vital signs, medication reconciliation and administration, and "
                "discharge diagnoses. Links to MIMIC-IV via subject_id."
            ),
            version="2.2",
            dataset_page_url="https://physionet.org/content/mimic-iv-ed/",
            dua_url="https://physionet.org/content/mimic-iv-ed/",
            bigquery_access_url="https://physionet.org/content/mimic-iv-ed/view-required-training/2.2/",
            file_listing_url="https://physionet.org/files/mimic-iv-ed/2.2/",
            subdirectories_to_scan=["ed"],
            expected_raw_subdirectories=["ed"],
            recommended_local_target_root="m4_data/raw_files/mimic-iv-ed",
            primary_verification_table="mimiciv_ed.edstays",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_ed"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            related_datasets={
                "mimic-iv": (
                    "Hospital and ICU data. Link via subject_id, or hadm_id for "
                    "stays that led to a hospital admission."
                ),
            },
            schema_mapping={"ed": "mimiciv_ed"},
            bigquery_schema_mapping={"mimiciv_ed": "mimiciv_ed"},
        )

        eicu_demo = DatasetDefinition(
            name="eicu-demo",
            title="eICU-CRD demo",
            description="eICU Collaborative Research Database Demo",
            summary=(
                "Open sample of the eICU Collaborative Research Database: over "
                "2,500 ICU unit stays from 20 of its larger US hospitals, "
                "2014-2015. For checking whether eICU-CRD fits a study before "
                "requesting access."
            ),
            version="2.0.1",
            download_size_gb=0.051,
            dataset_page_url="https://physionet.org/content/eicu-crd-demo/",
            file_listing_url="https://physionet.org/files/eicu-crd-demo/2.0.1/",
            subdirectories_to_scan=[],
            expected_raw_subdirectories=[],
            recommended_local_target_root="m4_data/raw_files/eicu-demo",
            primary_verification_table="eicu_crd.patient",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["eicu_crd_demo"],
            modalities=frozenset({Modality.TABULAR}),
            # Same canonical schema as the full eicu, so the same SQL runs on both
            schema_mapping={"": "eicu_crd"},
            bigquery_schema_mapping={"eicu_crd": "eicu_crd_demo"},
        )

        eicu = DatasetDefinition(
            name="eicu",
            title="eICU-CRD",
            description="eICU Collaborative Research Database",
            summary=(
                "ICU stays from 208 US hospitals in the Philips eICU telehealth "
                "program, 2014-2015: over 200,000 unit stays of over 139,000 "
                "patients, with vital signs, labs, medications, APACHE severity "
                "scores, diagnoses and care plans."
            ),
            version="2.0",
            dataset_page_url="https://physionet.org/content/eicu-crd/",
            dua_url="https://physionet.org/content/eicu-crd/",
            bigquery_access_url="https://physionet.org/content/eicu-crd/view-required-training/2.0/",
            file_listing_url="https://physionet.org/files/eicu-crd/2.0/",
            subdirectories_to_scan=[],
            expected_raw_subdirectories=[],
            recommended_local_target_root="m4_data/raw_files/eicu",
            primary_verification_table="eicu_crd.patient",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["eicu_crd"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            schema_mapping={"": "eicu_crd"},
            bigquery_schema_mapping={"eicu_crd": "eicu_crd"},
        )

        mimic_iii = DatasetDefinition(
            name="mimic-iii",
            title="MIMIC-III",
            description="MIMIC-III Clinical Database",
            summary=(
                "Records of over 40,000 patients who stayed in the critical care "
                "units of Beth Israel Deaconess Medical Center in Boston, "
                "2001-2012: demographics, hourly vital signs, labs, procedures, "
                "medications, caregiver notes, imaging reports and mortality."
            ),
            version="1.4",
            dataset_page_url="https://physionet.org/content/mimiciii/",
            dua_url="https://physionet.org/content/mimiciii/",
            bigquery_access_url="https://physionet.org/content/mimiciii/view-required-training/1.4/",
            file_listing_url="https://physionet.org/files/mimiciii/1.4/",
            subdirectories_to_scan=[],
            expected_raw_subdirectories=[],
            recommended_local_target_root="m4_data/raw_files/mimic-iii",
            # Files are named in upper case (ADMISSIONS.csv.gz); views are not.
            primary_verification_table="mimiciii_clinical.admissions",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciii_clinical"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            schema_mapping={"": "mimiciii_clinical"},
            bigquery_schema_mapping={"mimiciii_clinical": "mimiciii_clinical"},
        )

        builtins = (
            mimic_iv_demo,
            mimic_iv,
            mimic_iv_note,
            mimic_iv_ed_demo,
            mimic_iv_ed,
            eicu_demo,
            eicu,
            mimic_iii,
        )
        for dataset in builtins:
            cls.register(dataset)
        cls._builtin_names = frozenset(dataset.name.lower() for dataset in builtins)


# Initialize registry
DatasetRegistry._register_builtins()
