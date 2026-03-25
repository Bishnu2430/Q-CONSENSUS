"""Artifact and event storage management for debate runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ArtifactStore:
    """Stores run artifacts (prompts, responses, metadata) separately from event stream."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        Path(base_dir).mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> str:
        return os.path.join(self.base_dir, run_id)

    def save_artifact(self, *, run_id: str, artifact_type: str, artifact_id: str, content: Any) -> None:
        """Save an artifact (e.g. prompt, response, metadata) for a run."""
        run_dir = self._run_dir(run_id)
        Path(run_dir).mkdir(parents=True, exist_ok=True)

        artifact_file = os.path.join(run_dir, f"{artifact_type}_{artifact_id}.json")
        with open(artifact_file, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    def load_artifact(self, *, run_id: str, artifact_type: str, artifact_id: str) -> Optional[Any]:
        """Load a stored artifact."""
        run_dir = self._run_dir(run_id)
        artifact_file = os.path.join(run_dir, f"{artifact_type}_{artifact_id}.json")

        if not os.path.exists(artifact_file):
            return None

        with open(artifact_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_artifacts(self, *, run_id: str, artifact_type: Optional[str] = None) -> list[str]:
        """List all artifacts for a run, optionally filtered by type."""
        run_dir = self._run_dir(run_id)
        if not os.path.isdir(run_dir):
            return []

        artifacts = []
        for filename in os.listdir(run_dir):
            if artifact_type is None or filename.startswith(f"{artifact_type}_"):
                artifacts.append(filename)

        return sorted(artifacts)

    def save_run_metadata(self, *, run_id: str, metadata: Dict[str, Any]) -> None:
        """Save run-level metadata."""
        self.save_artifact(run_id=run_id, artifact_type="metadata", artifact_id="run", content=metadata)

    def load_run_metadata(self, *, run_id: str) -> Optional[Dict[str, Any]]:
        """Load run metadata."""
        return self.load_artifact(run_id=run_id, artifact_type="metadata", artifact_id="run")
