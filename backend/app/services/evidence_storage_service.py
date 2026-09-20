"""Backward-compatible alias module.

`EvidenceStorage`/`LocalEvidenceStorage` used to be their own class
hierarchy, duplicated with `ReportStorage`/`LocalReportStorage`
(report_storage_service.py). Fase 4A unified both into a single
`ArtifactStorage` hierarchy (app/services/artifact_storage.py) that also
supports an S3-compatible backend. This module re-exports the same names
from the same import path so every existing call site — service
constructors, tests that construct `LocalEvidenceStorage(root, max_file_mb)`
directly — keeps working unmodified.
"""

from app.services.artifact_storage import ArtifactStorage as EvidenceStorage
from app.services.artifact_storage import LocalArtifactStorage as LocalEvidenceStorage

__all__ = ["EvidenceStorage", "LocalEvidenceStorage"]
