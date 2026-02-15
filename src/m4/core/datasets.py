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
        version: Dataset version string
        file_listing_url: URL for downloading dataset files
        subdirectories_to_scan: Directories to scan for data files
        default_duckdb_filename: Default filename for local DuckDB database
        primary_verification_table: Table to check for dataset verification
        bigquery_project_id: Google Cloud project ID for BigQuery access
        bigquery_dataset_ids: BigQuery dataset IDs containing the tables
        requires_authentication: Whether dataset requires auth (e.g., credentialed access)
        modalities: Immutable set of data modalities (TABULAR, NOTES, etc.)
        related_datasets: Cross-references to related datasets with linkage info
    """

    name: str
    description: str = ""
    version: str = "1.0"
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

    # Filesystem directory -> canonical schema name
    # e.g. {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"}
    # Root-level files use empty string key: {"": "eicu_crd"}
    schema_mapping: dict[str, str] = field(default_factory=dict)

    # Canonical schema -> BigQuery dataset ID
    # e.g. {"mimiciv_hosp": "mimiciv_hosp"}
    bigquery_schema_mapping: dict[str, str] = field(default_factory=dict)

    # Table descriptions: schema.table -> short description
    table_descriptions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.default_duckdb_filename:
            self.default_duckdb_filename = f"{self.name.replace('-', '_')}.duckdb"


# ---------------------------------------------------------------------------
# Table descriptions for built-in datasets
# ---------------------------------------------------------------------------

MIMIC_IV_HOSP_TABLE_DESCRIPTIONS: dict[str, str] = {
    "mimiciv_hosp.admissions": "Hospital admissions and discharge information",
    "mimiciv_hosp.d_hcpcs": "HCPCS code definitions",
    "mimiciv_hosp.d_icd_diagnoses": "ICD diagnosis code definitions",
    "mimiciv_hosp.d_icd_procedures": "ICD procedure code definitions",
    "mimiciv_hosp.d_labitems": "Laboratory item definitions (itemid → label, fluid, category)",
    "mimiciv_hosp.diagnoses_icd": "Hospital diagnoses coded in ICD-9/10",
    "mimiciv_hosp.drgcodes": "Diagnosis-related group (DRG) codes per admission",
    "mimiciv_hosp.emar": "Electronic medication administration records",
    "mimiciv_hosp.emar_detail": "Detailed fields for each eMAR administration",
    "mimiciv_hosp.hcpcsevents": "HCPCS events during hospital stay",
    "mimiciv_hosp.labevents": "Laboratory measurements (chemistry, hematology, blood gas, etc.)",
    "mimiciv_hosp.microbiologyevents": "Microbiology cultures and sensitivities",
    "mimiciv_hosp.omr": "Outpatient medical record observations (BMI, blood pressure, etc.)",
    "mimiciv_hosp.patients": "Patient demographics (gender, anchor age, date of death)",
    "mimiciv_hosp.pharmacy": "Pharmacy orders and medication details",
    "mimiciv_hosp.poe": "Provider order entry records",
    "mimiciv_hosp.poe_detail": "Detailed fields for each provider order",
    "mimiciv_hosp.prescriptions": "Medication prescriptions",
    "mimiciv_hosp.procedures_icd": "Hospital procedures coded in ICD-9/10",
    "mimiciv_hosp.services": "Hospital service assignments per admission",
    "mimiciv_hosp.transfers": "Patient transfers between care units",
}

MIMIC_IV_ICU_TABLE_DESCRIPTIONS: dict[str, str] = {
    "mimiciv_icu.caregiver": "Caregiver (nurse/physician) identifiers",
    "mimiciv_icu.chartevents": "Charted observations (vitals, assessments) in the ICU",
    "mimiciv_icu.d_items": "ICU item definitions (itemid → label, category, unit)",
    "mimiciv_icu.datetimeevents": "Date/time events recorded in the ICU",
    "mimiciv_icu.icustays": "ICU stays with admission/discharge times and unit type",
    "mimiciv_icu.ingredientevents": "Continuous infusion ingredient-level data",
    "mimiciv_icu.inputevents": "Fluids and medications administered in the ICU",
    "mimiciv_icu.outputevents": "Patient outputs (urine, drains, etc.) in the ICU",
    "mimiciv_icu.procedureevents": "Procedures performed during ICU stay",
}

MIMIC_IV_DERIVED_TABLE_DESCRIPTIONS: dict[str, str] = {
    "mimiciv_derived.age": "Patient age at ICU admission",
    "mimiciv_derived.antibiotic": "Antibiotic administrations",
    "mimiciv_derived.apsiii": "APACHE III severity score",
    "mimiciv_derived.blood_differential": "Blood differential (bands, lymphocytes, etc.)",
    "mimiciv_derived.cardiac_marker": "Cardiac biomarkers (troponin, BNP)",
    "mimiciv_derived.chemistry": "Blood chemistry panel (BUN, creatinine, glucose, etc.)",
    "mimiciv_derived.coagulation": "Coagulation studies (PT, INR, PTT)",
    "mimiciv_derived.complete_blood_count": "Complete blood count (WBC, hemoglobin, platelets)",
    "mimiciv_derived.creatinine_baseline": "Estimated baseline creatinine",
    "mimiciv_derived.enzyme": "Enzyme levels (ALT, AST, LDH, etc.)",
    "mimiciv_derived.first_day_bg": "First-day arterial blood gas values",
    "mimiciv_derived.first_day_bg_art": "First-day arterial blood gas (arterial only)",
    "mimiciv_derived.first_day_gcs": "First-day Glasgow Coma Scale",
    "mimiciv_derived.first_day_height": "First-day patient height",
    "mimiciv_derived.first_day_lab": "First-day laboratory values",
    "mimiciv_derived.first_day_sofa": "First-day SOFA score",
    "mimiciv_derived.first_day_urine_output": "First-day urine output",
    "mimiciv_derived.first_day_vitalsign": "First-day vital signs",
    "mimiciv_derived.first_day_weight": "First-day patient weight",
    "mimiciv_derived.gcs": "Glasgow Coma Scale over time",
    "mimiciv_derived.height": "Patient height measurements",
    "mimiciv_derived.icustay_detail": "Extended ICU stay details (age, LOS, mortality)",
    "mimiciv_derived.icustay_hourly": "Hourly timestamps for each ICU stay",
    "mimiciv_derived.icustay_times": "ICU stay start/end times",
    "mimiciv_derived.inflammation": "Inflammatory markers (CRP, procalcitonin)",
    "mimiciv_derived.invasive_line": "Invasive line placements (arterial, central, etc.)",
    "mimiciv_derived.kdigo_creatinine": "KDIGO AKI staging (creatinine criteria)",
    "mimiciv_derived.kdigo_stages": "KDIGO AKI combined staging",
    "mimiciv_derived.kdigo_uo": "KDIGO AKI staging (urine output criteria)",
    "mimiciv_derived.lods": "LODS organ dysfunction score",
    "mimiciv_derived.meld": "MELD score for liver disease severity",
    "mimiciv_derived.norepinephrine_equivalent_dose": "Vasopressor dose in norepinephrine equivalents",
    "mimiciv_derived.oasis": "OASIS severity score",
    "mimiciv_derived.oxygen_delivery": "Oxygen delivery device and settings",
    "mimiciv_derived.rrt": "Renal replacement therapy episodes",
    "mimiciv_derived.sapsii": "SAPS-II severity score",
    "mimiciv_derived.sepsis3": "Sepsis-3 episodes (SOFA >= 2 + suspected infection)",
    "mimiciv_derived.sofa": "Sequential Organ Failure Assessment score",
    "mimiciv_derived.suspicion_of_infection": "Suspected infection (antibiotics + cultures)",
    "mimiciv_derived.urine_output": "Hourly urine output",
    "mimiciv_derived.urine_output_rate": "Urine output rate (mL/kg/hr)",
    "mimiciv_derived.vasoactive_agent": "Vasoactive agent administrations",
    "mimiciv_derived.ventilation": "Mechanical ventilation episodes and settings",
    "mimiciv_derived.vitalsign": "Vital signs over time (heart rate, BP, SpO2, etc.)",
    "mimiciv_derived.weight_durations": "Weight measurements with duration of validity",
}

EICU_TABLE_DESCRIPTIONS: dict[str, str] = {
    "eicu_crd.admissiondx": "Admission diagnoses from APACHE",
    "eicu_crd.admissiondrug": "Pre-admission medications",
    "eicu_crd.allergy": "Patient allergies",
    "eicu_crd.apacheapsvar": "APACHE APS variables",
    "eicu_crd.apachepatientresult": "APACHE IV/IVa predictions and scores",
    "eicu_crd.apachepredvar": "APACHE prediction variables",
    "eicu_crd.careplancareprovider": "Care provider assignments",
    "eicu_crd.careplaneol": "End-of-life care plan entries",
    "eicu_crd.careplangeneral": "General care plan entries",
    "eicu_crd.careplangoal": "Care plan goals",
    "eicu_crd.careplaninfectiousdisease": "Infectious disease care plan entries",
    "eicu_crd.customlab": "Custom laboratory results",
    "eicu_crd.diagnosis": "Patient diagnoses",
    "eicu_crd.hospital": "Hospital characteristics (region, bed count, teaching status)",
    "eicu_crd.infusiondrug": "Continuous infusion drug data",
    "eicu_crd.intakeoutput": "Intake and output measurements",
    "eicu_crd.lab": "Laboratory results",
    "eicu_crd.medication": "Medication orders",
    "eicu_crd.microlab": "Microbiology culture results",
    "eicu_crd.note": "Clinical notes and assessments",
    "eicu_crd.nurseassessment": "Nursing assessment data",
    "eicu_crd.nursecare": "Nursing care interventions",
    "eicu_crd.nursecharting": "Nursing charting (vitals and observations)",
    "eicu_crd.pasthistory": "Patient past medical history",
    "eicu_crd.patient": "Patient demographics and ICU stay info",
    "eicu_crd.physicalexam": "Physical examination findings",
    "eicu_crd.respiratorycare": "Respiratory care and ventilator settings",
    "eicu_crd.respiratorycharting": "Respiratory therapy charting",
    "eicu_crd.treatment": "Treatment interventions",
    "eicu_crd.vitalaperiodic": "Aperiodic vital signs (invasive BP)",
    "eicu_crd.vitalperiodic": "Periodic vital signs (HR, SpO2, etc.)",
}


class DatasetRegistry:
    """Registry for managing dataset definitions.

    This class maintains a global registry of available datasets with
    enhanced capability metadata.
    """

    _registry: ClassVar[dict[str, DatasetDefinition]] = {}

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
    def get_active(cls) -> DatasetDefinition:
        """Get the currently active dataset definition.

        This method retrieves the active dataset from config and returns
        its definition. Raises an error if no active dataset is configured.

        Returns:
            DatasetDefinition for the active dataset

        Raises:
            DatasetError: If no active dataset is configured or dataset not found
        """
        # Import here to avoid circular dependency
        from m4.config import get_active_dataset

        active_ds_name = get_active_dataset()
        if not active_ds_name:
            raise DatasetError(
                "No active dataset configured. "
                "Use `set_dataset('dataset-name')` to select a dataset."
            )

        ds_def = cls.get(active_ds_name)
        if not ds_def:
            raise DatasetError(
                f"Active dataset '{active_ds_name}' not found in registry. "
                f"Available datasets: {', '.join(d.name for d in cls.list_all())}"
            )

        return ds_def

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
                data.setdefault("table_descriptions", {})

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
        mimic_iv_demo = DatasetDefinition(
            name="mimic-iv-demo",
            description="MIMIC-IV Clinical Database Demo",
            file_listing_url="https://physionet.org/files/mimic-iv-demo/2.2/",
            subdirectories_to_scan=["hosp", "icu"],
            primary_verification_table="mimiciv_hosp.admissions",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
            modalities=frozenset({Modality.TABULAR}),
            schema_mapping={"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"},
            table_descriptions={
                **MIMIC_IV_HOSP_TABLE_DESCRIPTIONS,
                **MIMIC_IV_ICU_TABLE_DESCRIPTIONS,
            },
        )

        mimic_iv = DatasetDefinition(
            name="mimic-iv",
            description="MIMIC-IV Clinical Database",
            file_listing_url="https://physionet.org/files/mimiciv/3.1/",
            subdirectories_to_scan=["hosp", "icu"],
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
            table_descriptions={
                **MIMIC_IV_HOSP_TABLE_DESCRIPTIONS,
                **MIMIC_IV_ICU_TABLE_DESCRIPTIONS,
                **MIMIC_IV_DERIVED_TABLE_DESCRIPTIONS,
            },
        )

        mimic_iv_note = DatasetDefinition(
            name="mimic-iv-note",
            description="MIMIC-IV Clinical Notes (discharge summaries, radiology reports)",
            file_listing_url="https://physionet.org/files/mimic-iv-note/2.2/",
            subdirectories_to_scan=["note"],
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

        eicu = DatasetDefinition(
            name="eicu",
            description="eICU Collaborative Research Database",
            file_listing_url="https://physionet.org/files/eicu-crd/2.0/",
            subdirectories_to_scan=[],
            primary_verification_table="eicu_crd.patient",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["eicu_crd"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            schema_mapping={"": "eicu_crd"},
            bigquery_schema_mapping={"eicu_crd": "eicu_crd"},
            table_descriptions=EICU_TABLE_DESCRIPTIONS,
        )

        cls.register(mimic_iv_demo)
        cls.register(mimic_iv)
        cls.register(mimic_iv_note)
        cls.register(eicu)


# Initialize registry
DatasetRegistry._register_builtins()
