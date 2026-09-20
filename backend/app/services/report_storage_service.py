"""Backward-compatible alias module — see evidence_storage_service.py for why
this re-exports from artifact_storage.py instead of defining its own class
hierarchy."""

from app.services.artifact_storage import ArtifactStorage as ReportStorage
from app.services.artifact_storage import LocalArtifactStorage as LocalReportStorage

__all__ = ["ReportStorage", "LocalReportStorage"]
