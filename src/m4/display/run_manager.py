"""Run-centric persistence manager for the display pipeline.

Manages multiple ArtifactStore instances (one per run), with runs persisting
across server restarts. Provides cross-run queries, request queue management,
and age-based cleanup.

Storage layout:
    {m4_data}/display/
    ├── runs.json              # Global registry
    ├── requests.json          # Request queue (display-level)
    ├── .server.json           # PID file (transient)
    └── runs/
        ├── 2025-06-09_103045_sepsis-mortality/
        │   ├── index.json     # Cards for this run
        │   ├── meta.json      # Run metadata (label, start_time)
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

from m4.display._types import CardDescriptor
from m4.display.artifacts import ArtifactStore

logger = logging.getLogger(__name__)


def _sanitize_label(label: str) -> str:
    """Sanitize a run label for use in directory names.

    Converts to lowercase, replaces non-alphanumeric chars with hyphens,
    collapses runs, strips leading/trailing hyphens, and truncates to 64 chars.
    """
    s = label.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:64] or "unnamed"


def _make_run_dir_name(label: str) -> str:
    """Generate a directory name for a run: {YYYY-MM-DD}_{HHMMSS}_{sanitized_label}."""
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


class RunManager:
    """Manages multiple runs, each backed by an ArtifactStore.

    Args:
        display_dir: Root display directory ({m4_data}/display/).
    """

    def __init__(self, display_dir: Path) -> None:
        self.display_dir = display_dir
        self._runs_dir = display_dir / "runs"
        self._registry_path = display_dir / "runs.json"
        self._requests_path = display_dir / "requests.json"

        # Ensure directories exist
        self._runs_dir.mkdir(parents=True, exist_ok=True)

        # In-memory state
        self._stores: dict[str, ArtifactStore] = {}  # dir_name -> ArtifactStore
        self._label_to_dir: dict[str, str] = {}  # user_label -> dir_name
        self._card_index: dict[str, str] = {}  # card_id -> dir_name

        # Discover existing runs from disk
        self._discover_runs()

    # --- Run Lifecycle ---

    def get_or_create_run(self, run_id: str | None = None) -> tuple[str, ArtifactStore]:
        """Get or create a run by label.

        If run_id is None, generates an auto-label from the current timestamp.
        If a run with the same label already exists (within RunManager lifetime),
        returns the existing run.

        Args:
            run_id: User-provided run label, or None for auto.

        Returns:
            Tuple of (run_id_label, ArtifactStore).
        """
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("auto-%Y%m%d-%H%M%S")

        # Return existing run if label matches
        if run_id in self._label_to_dir:
            dir_name = self._label_to_dir[run_id]
            if dir_name in self._stores:
                return run_id, self._stores[dir_name]
            # Rebuild store if somehow evicted
            return run_id, self._load_run(dir_name)

        # Create new run
        dir_name = _make_run_dir_name(run_id)
        run_dir = self._runs_dir / dir_name
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write run metadata
        meta = {
            "label": run_id,
            "dir_name": dir_name,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        # Create ArtifactStore
        store = ArtifactStore(session_dir=run_dir, session_id=dir_name)
        self._stores[dir_name] = store
        self._label_to_dir[run_id] = dir_name

        # Update registry
        self._add_to_registry(run_id, dir_name, meta["start_time"])

        logger.debug(f"Created run '{run_id}' -> {dir_name}")
        return run_id, store

    def ensure_run_loaded(self, dir_name: str) -> ArtifactStore | None:
        """Ensure a run directory is loaded into memory.

        Used by the server to lazily discover run dirs created by clients.

        Args:
            dir_name: Run directory name.

        Returns:
            ArtifactStore if the directory exists, None otherwise.
        """
        if dir_name in self._stores:
            return self._stores[dir_name]

        run_dir = self._runs_dir / dir_name
        if not run_dir.exists():
            return None

        return self._load_run(dir_name)

    def delete_run(self, run_id: str) -> bool:
        """Delete a run by label.

        Removes the run directory and updates the registry.

        Args:
            run_id: The run label to delete.

        Returns:
            True if the run was deleted, False if not found.
        """
        dir_name = self._label_to_dir.get(run_id)
        if dir_name is None:
            return False

        # Remove from disk
        run_dir = self._runs_dir / dir_name
        if run_dir.exists():
            shutil.rmtree(run_dir)

        # Clean up in-memory state
        self._stores.pop(dir_name, None)
        self._label_to_dir.pop(run_id, None)

        # Remove card index entries for this run
        to_remove = [cid for cid, dn in self._card_index.items() if dn == dir_name]
        for cid in to_remove:
            del self._card_index[cid]

        # Update registry
        self._remove_from_registry(dir_name)

        logger.debug(f"Deleted run '{run_id}' ({dir_name})")
        return True

    def clean_runs(self, older_than: str = "7d") -> int:
        """Remove runs older than a given age.

        Args:
            older_than: Age string (e.g., '7d', '24h', '0d' for all).

        Returns:
            Number of runs removed.
        """
        max_age_secs = _parse_age(older_than)
        now = time.time()
        removed = 0

        # Snapshot labels to avoid modifying dict during iteration
        labels = list(self._label_to_dir.keys())
        for label in labels:
            dir_name = self._label_to_dir[label]
            run_dir = self._runs_dir / dir_name
            meta_path = run_dir / "meta.json"

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

            if self.delete_run(label):
                removed += 1

        return removed

    # --- Cross-Run Queries ---

    def list_runs(self) -> list[dict[str, Any]]:
        """List all runs with metadata and card counts.

        Returns:
            List of dicts with label, dir_name, start_time, card_count,
            sorted newest first.
        """
        runs = []
        for label, dir_name in self._label_to_dir.items():
            run_dir = self._runs_dir / dir_name
            meta_path = run_dir / "meta.json"

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
                index_path = run_dir / "index.json"
                if index_path.exists():
                    try:
                        cards = json.loads(index_path.read_text())
                        card_count = len(cards)
                    except (json.JSONDecodeError, OSError):
                        pass

            runs.append(
                {
                    "label": label,
                    "dir_name": dir_name,
                    "start_time": start_time,
                    "card_count": card_count,
                }
            )

        # Sort newest first
        runs.sort(key=lambda r: r.get("start_time") or "", reverse=True)
        return runs

    def list_all_cards(self, run_id: str | None = None) -> list[CardDescriptor]:
        """List cards across all runs, or filtered by run label.

        Args:
            run_id: If provided, filter to cards from this run label.

        Returns:
            List of CardDescriptors.
        """
        if run_id is not None:
            dir_name = self._label_to_dir.get(run_id)
            if dir_name is None:
                return []
            store = self._stores.get(dir_name)
            if store is None:
                return []
            return store.list_cards()

        # All cards from all runs
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

    def register_card(self, card_id: str, dir_name: str) -> None:
        """Register a card in the cross-run card index.

        Args:
            card_id: The card's unique ID.
            dir_name: The run directory name containing this card.
        """
        self._card_index[card_id] = dir_name

    # --- Request Queue (display-level) ---

    def store_request(self, request: dict[str, Any]) -> None:
        """Append a request to the display-level request queue."""
        requests = self._read_requests()
        request.setdefault("acknowledged", False)
        requests.append(request)
        self._requests_path.write_text(json.dumps(requests, indent=2))

    def _read_requests(self) -> list[dict[str, Any]]:
        """Read the request queue from disk."""
        if not self._requests_path.exists():
            return []
        try:
            return json.loads(self._requests_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def list_requests(self, pending_only: bool = True) -> list[dict[str, Any]]:
        """List requests from the queue.

        Args:
            pending_only: If True, only return unacknowledged requests.
        """
        requests = self._read_requests()
        if pending_only:
            requests = [r for r in requests if not r.get("acknowledged", False)]
        return requests

    def acknowledge_request(self, request_id: str) -> None:
        """Mark a request as acknowledged."""
        requests = self._read_requests()
        for r in requests:
            if r.get("request_id") == request_id:
                r["acknowledged"] = True
                break
        self._requests_path.write_text(json.dumps(requests, indent=2))

    def store_selection(self, selection_id: str, rows: list, columns: list) -> Path:
        """Store a selection as a Parquet artifact in the display-level dir.

        Used for cross-run selections where no specific run is appropriate.
        Falls back to the first available store.
        """
        # Use the first available store (or create a temp one)
        for store in self._stores.values():
            return store.store_selection(selection_id, rows, columns)
        # Fallback: create an artifacts dir at display level
        artifacts_dir = self.display_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        import pandas as pd

        df = pd.DataFrame(rows, columns=columns)
        path = artifacts_dir / f"{selection_id}.parquet"
        df.to_parquet(path, index=False)
        return path

    def store_selection_json(self, selection_id: str, data: dict[str, Any]) -> Path:
        """Store a chart point selection as JSON at display level."""
        for store in self._stores.values():
            return store.store_selection_json(selection_id, data)
        # Fallback
        artifacts_dir = self.display_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        path = artifacts_dir / f"{selection_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    # --- Internal ---

    def refresh(self) -> None:
        """Scan for new run directories created since the last discovery.

        Only loads runs not already known in memory. Safe to call frequently
        (e.g. before listing runs) since it skips known directories.
        """
        if not self._runs_dir.exists():
            return

        for run_dir in self._runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            dir_name = run_dir.name
            if dir_name in self._stores:
                continue  # Already known

            meta_path = run_dir / "meta.json"
            label = dir_name  # fallback
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    label = meta.get("label", dir_name)
                except (json.JSONDecodeError, OSError):
                    pass

            self._label_to_dir[label] = dir_name
            self._load_run(dir_name)

    def _discover_runs(self) -> None:
        """Scan existing run directories and rebuild in-memory state."""
        if not self._runs_dir.exists():
            return

        for run_dir in sorted(self._runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue

            dir_name = run_dir.name
            meta_path = run_dir / "meta.json"

            # Read label from meta.json
            label = dir_name  # fallback
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    label = meta.get("label", dir_name)
                except (json.JSONDecodeError, OSError):
                    pass

            self._label_to_dir[label] = dir_name
            self._load_run(dir_name)

    def _load_run(self, dir_name: str) -> ArtifactStore:
        """Load a run directory into memory and index its cards."""
        run_dir = self._runs_dir / dir_name
        store = ArtifactStore(session_dir=run_dir, session_id=dir_name)
        self._stores[dir_name] = store

        # Index cards
        for card in store.list_cards():
            self._card_index[card.card_id] = dir_name

        return store

    def _read_registry(self) -> list[dict[str, Any]]:
        """Read the global runs registry from disk."""
        if not self._registry_path.exists():
            return []
        try:
            return json.loads(self._registry_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_registry(self, runs: list[dict[str, Any]]) -> None:
        """Write the global runs registry to disk."""
        self._registry_path.write_text(json.dumps(runs, indent=2))

    def _add_to_registry(self, label: str, dir_name: str, start_time: str) -> None:
        """Add a run entry to the registry."""
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
        """Remove a run entry from the registry by dir_name."""
        registry = self._read_registry()
        registry = [r for r in registry if r.get("dir_name") != dir_name]
        self._write_registry(registry)
