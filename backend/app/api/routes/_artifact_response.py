"""Shared helper turning an `ArtifactDownload` into the right HTTP response.

Every artifact download route (evidence, election-day documents, election
act evidence, report artifacts) authorizes first through its service layer,
then renders whatever that service handed back — a local `Path` streamed via
`FileResponse`, or a presigned URL the browser is redirected to so FastAPI
never transports the bytes itself (§19/§50 Fase 4A)."""

from fastapi.responses import FileResponse, RedirectResponse

from app.services.artifact_storage import LocalArtifactDownload, RemoteArtifactDownload

_PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def artifact_response(download, *, media_type: str | None, filename: str | None):
    if isinstance(download, LocalArtifactDownload):
        return FileResponse(download.path, media_type=media_type, filename=filename, headers=_PRIVATE_HEADERS)
    if isinstance(download, RemoteArtifactDownload):
        return RedirectResponse(download.url, status_code=307, headers=_PRIVATE_HEADERS)
    raise TypeError(f"Tipo de descarga de artefacto no soportado: {type(download)!r}")
