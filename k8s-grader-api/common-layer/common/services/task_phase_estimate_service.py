"""Exact task and phase timing estimate lookup."""
from __future__ import annotations

from typing import Dict, Optional

from common.database import TaskPhaseEstimateRepository
from common.models.task_manifest import TaskManifest


class TaskPhaseEstimateService:
    """Look up exact saved timing data without fallback."""

    def __init__(self, estimate_repo: Optional[TaskPhaseEstimateRepository] = None):
        self.estimate_repo = estimate_repo or TaskPhaseEstimateRepository()

    def get_phase_estimate_seconds(self, game: str, task_id: str, phase_id: Optional[str]) -> Optional[float]:
        if not phase_id:
            return None
        item = self.estimate_repo.get(game, task_id, phase_id)
        if not item:
            return None
        duration = item.get("durationSeconds")
        return float(duration) if duration is not None else None

    @staticmethod
    def _required_phases(manifest: TaskManifest) -> list:
        phases = getattr(manifest, "phases", [])
        if isinstance(phases, dict):
            phases = list(phases.values())
        return [phase for phase in phases if getattr(phase, "required", True)]

    def get_estimate_payload(
        self,
        game: str,
        task_id: str,
        *,
        current_phase_id: Optional[str] = None,
        manifest: Optional[TaskManifest] = None,
    ) -> Dict[str, float]:
        resolved_manifest = manifest or TaskManifest.load(game, task_id)
        estimates = {item["phase"]: float(item["durationSeconds"]) for item in self.estimate_repo.list_by_task(game, task_id)}
        payload: Dict[str, float] = {}

        current_phase_seconds = self.get_phase_estimate_seconds(game, task_id, current_phase_id)
        if current_phase_seconds is not None:
            payload["estimated_phase_seconds"] = round(current_phase_seconds, 2)

        required_phases = self._required_phases(resolved_manifest)
        if required_phases and all(phase.id in estimates for phase in required_phases):
            payload["estimated_task_seconds"] = round(sum(estimates[phase.id] for phase in required_phases), 2)

        if current_phase_id:
            remaining_phases = []
            phase_seen = False
            for phase in required_phases:
                if phase.id == current_phase_id:
                    phase_seen = True
                if phase_seen:
                    remaining_phases.append(phase)
            if remaining_phases and all(phase.id in estimates for phase in remaining_phases):
                payload["estimated_remaining_task_seconds"] = round(
                    sum(estimates[phase.id] for phase in remaining_phases),
                    2,
                )

        return payload
