"""Study-centric persistence manager for the vitrine pipeline.

Manages multiple ArtifactStore instances (one per study), with studies persisting
across server restarts. Provides cross-study queries and age-based cleanup.

Storage layout:
    {project_root}/.vitrine/
    ├── studies.json            # Global registry
    ├── .server.json            # PID file (transient)
    └── studies/
        ├── 2025-06-09_103045_sepsis-mortality/
        │   ├── index.json     # Cards for this study
        │   ├── meta.json      # Study metadata (label, start_time)
        │   └── artifacts/     # Parquet, JSON, SVG files
        └── ...
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from m4.vitrine._types import CardDescriptor
from m4.vitrine.artifacts import ArtifactStore

logger = logging.getLogger(__name__)


def _sanitize_label(label: str) -> str:
    """Sanitize a study label for use in directory names.

    Converts to lowercase, replaces non-alphanumeric chars with hyphens,
    collapses runs, strips leading/trailing hyphens, and truncates to 64 chars.
    """
    s = label.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:64] or "unnamed"


def _make_study_dir_name(label: str) -> str:
    """Generate a directory name for a study: {YYYY-MM-DD}_{HHMMSS}_{sanitized_label}."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%d_%H%M%S")
    return f"{ts}_{_sanitize_label(label)}"


def _parse_age(age_str: str) -> float:
    """Parse a duration string like '7d', '24h', '30m' into seconds.

    Supported suffixes: d (days), h (hours), m (minutes), s (seconds).
    Plain integer is treated as seconds.
    """
    age_str = age_str.strip()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([dhms]?)$", age_str, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid age string: {age_str!r} (expected e.g. '7d', '24h')")
    value = float(match.group(1))
    unit = match.group(2).lower() or "s"
    multipliers = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return value * multipliers[unit]


class StudyManager:
    """Manages multiple studies, each backed by an ArtifactStore.

    Args:
        vitrine_dir: Root vitrine directory ({project_root}/.vitrine/).
    """

    def __init__(self, vitrine_dir: Path) -> None:
        self.display_dir = vitrine_dir
        self._studies_dir = vitrine_dir / "studies"
        self._registry_path = vitrine_dir / "studies.json"
        # Ensure directories exist
        self._studies_dir.mkdir(parents=True, exist_ok=True)

        # In-memory state
        self._stores: dict[str, ArtifactStore] = {}  # dir_name -> ArtifactStore
        self._label_to_dir: dict[str, str] = {}  # user_label -> dir_name
        self._card_index: dict[str, str] = {}  # card_id -> dir_name

        # Discover existing studies from disk
        self._discover_studies()

    # --- Study Lifecycle ---

    def get_or_create_study(
        self, study: str | None = None
    ) -> tuple[str, ArtifactStore]:
        """Get or create a study by label.

        If study is None, generates an auto-label from the current timestamp.
        If a study with the same label already exists (within StudyManager lifetime),
        returns the existing study.

        Args:
            study: User-provided study label, or None for auto.

        Returns:
            Tuple of (study_label, ArtifactStore).
        """
        if study is None:
            study = datetime.now(timezone.utc).strftime("auto-%Y%m%d-%H%M%S")

        # Return existing study if label matches
        if study in self._label_to_dir:
            dir_name = self._label_to_dir[study]
            if dir_name in self._stores:
                return study, self._stores[dir_name]
            # Rebuild store if somehow evicted
            return study, self._load_study(dir_name)

        # Create new study
        dir_name = _make_study_dir_name(study)
        study_dir = self._studies_dir / dir_name
        study_dir.mkdir(parents=True, exist_ok=True)

        # Write study metadata
        meta = {
            "label": study,
            "dir_name": dir_name,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
        (study_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        # Create ArtifactStore
        store = ArtifactStore(session_dir=study_dir, session_id=dir_name)
        self._stores[dir_name] = store
        self._label_to_dir[study] = dir_name

        # Update registry
        self._add_to_registry(study, dir_name, meta["start_time"])

        logger.debug(f"Created study '{study}' -> {dir_name}")
        return study, store

    def ensure_study_loaded(self, dir_name: str) -> ArtifactStore | None:
        """Ensure a study directory is loaded into memory.

        Used by the server to lazily discover study dirs created by clients.

        Args:
            dir_name: Study directory name.

        Returns:
            ArtifactStore if the directory exists, None otherwise.
        """
        if dir_name in self._stores:
            return self._stores[dir_name]

        study_dir = self._studies_dir / dir_name
        if not study_dir.exists():
            return None

        return self._load_study(dir_name)

    def delete_study(self, study: str) -> bool:
        """Delete a study by label.

        Removes the study directory and updates the registry.

        Args:
            study: The study label to delete.

        Returns:
            True if the study was deleted, False if not found.
        """
        dir_name = self._label_to_dir.get(study)
        if dir_name is None:
            return False

        # Remove from disk
        study_dir = self._studies_dir / dir_name
        if study_dir.exists():
            shutil.rmtree(study_dir)

        # Clean up in-memory state
        self._stores.pop(dir_name, None)
        self._label_to_dir.pop(study, None)

        # Remove card index entries for this study
        to_remove = [cid for cid, dn in self._card_index.items() if dn == dir_name]
        for cid in to_remove:
            del self._card_index[cid]

        # Update registry
        self._remove_from_registry(dir_name)

        logger.debug(f"Deleted study '{study}' ({dir_name})")
        return True

    def rename_study(self, old_label: str, new_label: str) -> bool:
        """Rename a study by changing its label.

        Args:
            old_label: Current study label.
            new_label: New study label (must not already exist).

        Returns:
            True if renamed, False if old_label not found or new_label taken.
        """
        if old_label not in self._label_to_dir:
            return False
        if new_label in self._label_to_dir:
            return False
        if not new_label.strip():
            return False

        dir_name = self._label_to_dir[old_label]

        # Update in-memory mapping
        del self._label_to_dir[old_label]
        self._label_to_dir[new_label] = dir_name

        # Update meta.json on disk
        study_dir = self._studies_dir / dir_name
        meta_path = study_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                meta["label"] = new_label
                meta_path.write_text(json.dumps(meta, indent=2))
            except (json.JSONDecodeError, OSError):
                pass

        # Update registry
        registry = self._read_registry()
        for entry in registry:
            if entry.get("dir_name") == dir_name:
                entry["label"] = new_label
                break
        self._write_registry(registry)

        logger.debug(f"Renamed study '{old_label}' -> '{new_label}' ({dir_name})")
        return True

    def clean_studies(self, older_than: str = "7d") -> int:
        """Remove studies older than a given age.

        Args:
            older_than: Age string (e.g., '7d', '24h', '0d' for all).

        Returns:
            Number of studies removed.
        """
        max_age_secs = _parse_age(older_than)
        now = time.time()
        removed = 0

        # Snapshot labels to avoid modifying dict during iteration
        labels = list(self._label_to_dir.keys())
        for label in labels:
            dir_name = self._label_to_dir[label]
            study_dir = self._studies_dir / dir_name
            meta_path = study_dir / "meta.json"

            start_time = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    start_time = meta.get("start_time")
                except (json.JSONDecodeError, OSError):
                    pass

            if start_time:
                try:
                    # Parse ISO timestamp
                    dt = datetime.fromisoformat(start_time)
                    age_secs = now - dt.timestamp()
                    if age_secs < max_age_secs:
                        continue
                except (ValueError, TypeError):
                    pass

            if self.delete_study(label):
                removed += 1

        return removed

    # --- Cross-Study Queries ---

    def list_studies(self) -> list[dict[str, Any]]:
        """List all studies with metadata and card counts.

        Returns:
            List of dicts with label, dir_name, start_time, card_count,
            sorted newest first.
        """
        studies = []
        for label, dir_name in self._label_to_dir.items():
            study_dir = self._studies_dir / dir_name
            meta_path = study_dir / "meta.json"

            start_time = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    start_time = meta.get("start_time")
                except (json.JSONDecodeError, OSError):
                    pass

            # Count cards lazily
            card_count = 0
            if dir_name in self._stores:
                card_count = len(self._stores[dir_name].list_cards())
            else:
                index_path = study_dir / "index.json"
                if index_path.exists():
                    try:
                        cards = json.loads(index_path.read_text())
                        card_count = len(cards)
                    except (json.JSONDecodeError, OSError):
                        pass

            studies.append(
                {
                    "label": label,
                    "dir_name": dir_name,
                    "start_time": start_time,
                    "card_count": card_count,
                }
            )

        # Sort newest first
        studies.sort(key=lambda r: r.get("start_time") or "", reverse=True)
        return studies

    def list_all_cards(self, study: str | None = None) -> list[CardDescriptor]:
        """List cards across all studies, or filtered by study label.

        Args:
            study: If provided, filter to cards from this study label.

        Returns:
            List of CardDescriptors.
        """
        if study is not None:
            dir_name = self._label_to_dir.get(study)
            if dir_name is None:
                return []
            store = self._stores.get(dir_name)
            if store is None:
                return []
            return store.list_cards()

        # All cards from all studies
        all_cards: list[CardDescriptor] = []
        for dir_name in self._label_to_dir.values():
            store = self._stores.get(dir_name)
            if store:
                all_cards.extend(store.list_cards())

        # Sort by timestamp
        all_cards.sort(key=lambda c: c.timestamp or "")
        return all_cards

    def get_store_for_card(self, card_id: str) -> ArtifactStore | None:
        """Look up which ArtifactStore contains a given card.

        Args:
            card_id: The card ID to look up.

        Returns:
            ArtifactStore if found, None otherwise.
        """
        dir_name = self._card_index.get(card_id)
        if dir_name is not None:
            return self._stores.get(dir_name)
        return None

    def build_context(self, study: str) -> dict[str, Any]:
        """Build a structured context summary for agent re-orientation.

        Returns study metadata, card list, resolved responses, and
        pending decision cards.

        Args:
            study: The study label to summarize.

        Returns:
            Dict with study, card_count, cards, decisions (back-compat),
            pending_responses, decisions_made, and current_selections
            (filled by server when available). Returns empty context if
            study not found.
        """
        dir_name = self._label_to_dir.get(study)
        if dir_name is None:
            return {
                "study": study,
                "card_count": 0,
                "cards": [],
                "decisions": [],
                "pending_responses": [],
                "decisions_made": [],
                "current_selections": {},
            }

        store = self._stores.get(dir_name)
        if store is None:
            return {
                "study": study,
                "card_count": 0,
                "cards": [],
                "decisions": [],
                "pending_responses": [],
                "decisions_made": [],
                "current_selections": {},
            }

        cards = store.list_cards()
        card_summaries = []
        pending_responses = []
        decisions_made = []

        for c in cards:
            summary: dict[str, Any] = {
                "card_id": c.card_id,
                "card_type": c.card_type.value,
                "title": c.title,
                "timestamp": c.timestamp,
                "response_requested": c.response_requested,
            }
            if c.annotations:
                summary["annotations"] = [
                    {"id": a["id"], "text": a["text"], "timestamp": a.get("timestamp")}
                    for a in c.annotations
                ]
            card_summaries.append(summary)

            if c.response_action:
                decisions_made.append(
                    {
                        "card_id": c.card_id,
                        "title": c.title,
                        "action": c.response_action,
                        "message": c.response_message,
                        "values": c.response_values or {},
                        "summary": c.response_summary,
                        "artifact_id": c.response_artifact_id,
                        "timestamp": c.response_timestamp,
                    }
                )

            if c.response_requested:
                pending_responses.append(
                    {
                        "card_id": c.card_id,
                        "title": c.title,
                        "prompt": c.prompt,
                    }
                )

        return {
            "study": study,
            "card_count": len(cards),
            "cards": card_summaries,
            "decisions": pending_responses,  # backwards-compat alias
            "pending_responses": pending_responses,
            "decisions_made": decisions_made,
            "current_selections": {},
        }

    def register_card(self, card_id: str, dir_name: str) -> None:
        """Register a card in the cross-study card index.

        Args:
            card_id: The card's unique ID.
            dir_name: The study directory name containing this card.
        """
        self._card_index[card_id] = dir_name

    def store_selection(self, selection_id: str, rows: list, columns: list) -> Path:
        """Store a selection as a Parquet artifact in the vitrine-level dir.

        Used for cross-study selections where no specific study is appropriate.
        Falls back to the first available store.
        """
        # Use the first available store (or create a temp one)
        for store in self._stores.values():
            return store.store_selection(selection_id, rows, columns)
        # Fallback: create an artifacts dir at vitrine level
        artifacts_dir = self.display_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        import pandas as pd

        df = pd.DataFrame(rows, columns=columns)
        path = artifacts_dir / f"{selection_id}.parquet"
        df.to_parquet(path, index=False)
        return path

    def store_selection_json(self, selection_id: str, data: dict[str, Any]) -> Path:
        """Store a chart point selection as JSON at vitrine level."""
        for store in self._stores.values():
            return store.store_selection_json(selection_id, data)
        # Fallback
        artifacts_dir = self.display_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        path = artifacts_dir / f"{selection_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    # --- Output Directory Management ---

    def register_output_dir(
        self, study_label: str, path: str | Path | None = None
    ) -> Path:
        """Register an output directory for a study.

        If path is None, creates ``{study_dir}/output/`` and stores
        a relative reference. If path is a string/Path, stores the
        absolute path as-is.

        Args:
            study_label: The study label.
            path: External directory path, or None for self-contained.

        Returns:
            Path to the output directory (created if needed).
        """
        dir_name = self._label_to_dir.get(study_label)
        if dir_name is None:
            raise ValueError(f"Study '{study_label}' not found")

        study_dir = self._studies_dir / dir_name

        if path is None:
            output_dir = study_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            rel = "output"
        else:
            output_dir = Path(path).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            rel = str(output_dir)

        # Persist in meta.json
        meta_path = study_dir / "meta.json"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        meta["output_dir"] = rel
        meta_path.write_text(json.dumps(meta, indent=2))

        return output_dir

    def get_output_dir(self, study_label: str) -> Path | None:
        """Get the output directory for a study.

        Args:
            study_label: The study label.

        Returns:
            Path to the output directory, or None if not registered.
        """
        dir_name = self._label_to_dir.get(study_label)
        if dir_name is None:
            return None

        study_dir = self._studies_dir / dir_name
        meta_path = study_dir / "meta.json"
        if not meta_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        output_ref = meta.get("output_dir")
        if output_ref is None:
            return None

        # Relative path → resolve against study dir
        output_path = Path(output_ref)
        if not output_path.is_absolute():
            output_path = study_dir / output_path

        if not output_path.exists():
            return None

        return output_path

    def list_output_files(self, study_label: str) -> list[dict[str, Any]]:
        """List files in a study's output directory.

        Args:
            study_label: The study label.

        Returns:
            List of dicts with name, path, size, modified, type, is_dir.
        """
        output_dir = self.get_output_dir(study_label)
        if output_dir is None or not output_dir.exists():
            return []

        _EXT_TYPES = {
            ".py": "python",
            ".r": "r",
            ".sql": "sql",
            ".md": "markdown",
            ".csv": "csv",
            ".parquet": "parquet",
            ".tsv": "csv",
            ".json": "data",
            ".yaml": "data",
            ".yml": "data",
            ".toml": "data",
            ".cfg": "text",
            ".txt": "text",
            ".log": "text",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".gif": "image",
            ".svg": "image",
            ".pdf": "pdf",
        }

        files: list[dict[str, Any]] = []
        for item in sorted(output_dir.rglob("*")):
            if item.name.startswith("."):
                continue
            rel = str(item.relative_to(output_dir))
            ext = item.suffix.lower()
            ftype = _EXT_TYPES.get(ext, "other")
            if item.is_dir():
                ftype = "directory"

            stat = item.stat()
            files.append(
                {
                    "name": item.name,
                    "path": rel,
                    "size": stat.st_size if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "type": ftype,
                    "is_dir": item.is_dir(),
                }
            )

        return files

    def get_output_file_path(self, study_label: str, rel_path: str) -> Path | None:
        """Resolve and validate a relative path within the output directory.

        Path-traversal safe: rejects paths that escape the output dir.

        Args:
            study_label: The study label.
            rel_path: Relative path within the output directory.

        Returns:
            Absolute Path if valid and exists, None otherwise.
        """
        output_dir = self.get_output_dir(study_label)
        if output_dir is None:
            return None

        try:
            resolved = (output_dir / rel_path).resolve()
        except (ValueError, OSError):
            return None

        # Path traversal check
        try:
            resolved.relative_to(output_dir.resolve())
        except ValueError:
            return None

        if not resolved.exists():
            return None

        return resolved

    # --- Internal ---

    def refresh(self) -> None:
        """Scan for new study directories created since the last discovery.

        Only loads studies not already known in memory. Safe to call frequently
        (e.g. before listing studies) since it skips known directories.
        """
        if not self._studies_dir.exists():
            return

        for study_dir in self._studies_dir.iterdir():
            if not study_dir.is_dir():
                continue

            dir_name = study_dir.name
            if dir_name in self._stores:
                continue  # Already known

            meta_path = study_dir / "meta.json"
            label = dir_name  # fallback
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    label = meta.get("label", dir_name)
                except (json.JSONDecodeError, OSError):
                    pass

            self._label_to_dir[label] = dir_name
            self._load_study(dir_name)

    def _discover_studies(self) -> None:
        """Scan existing study directories and rebuild in-memory state."""
        if not self._studies_dir.exists():
            return

        for study_dir in sorted(self._studies_dir.iterdir()):
            if not study_dir.is_dir():
                continue

            dir_name = study_dir.name
            meta_path = study_dir / "meta.json"

            # Read label from meta.json
            label = dir_name  # fallback
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    label = meta.get("label", dir_name)
                except (json.JSONDecodeError, OSError):
                    pass

            self._label_to_dir[label] = dir_name
            self._load_study(dir_name)

    def _load_study(self, dir_name: str) -> ArtifactStore:
        """Load a study directory into memory and index its cards."""
        study_dir = self._studies_dir / dir_name
        store = ArtifactStore(session_dir=study_dir, session_id=dir_name)
        self._stores[dir_name] = store

        # Index cards
        for card in store.list_cards():
            self._card_index[card.card_id] = dir_name

        return store

    def _read_registry(self) -> list[dict[str, Any]]:
        """Read the global studies registry from disk."""
        if not self._registry_path.exists():
            return []
        try:
            return json.loads(self._registry_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_registry(self, studies: list[dict[str, Any]]) -> None:
        """Write the global studies registry to disk."""
        self._registry_path.write_text(json.dumps(studies, indent=2))

    def _add_to_registry(self, label: str, dir_name: str, start_time: str) -> None:
        """Add a study entry to the registry."""
        registry = self._read_registry()
        registry.append(
            {
                "label": label,
                "dir_name": dir_name,
                "start_time": start_time,
            }
        )
        self._write_registry(registry)

    def _remove_from_registry(self, dir_name: str) -> None:
        """Remove a study entry from the registry by dir_name."""
        registry = self._read_registry()
        registry = [r for r in registry if r.get("dir_name") != dir_name]
        self._write_registry(registry)
