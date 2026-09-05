import re

# Signature-based sniffing (never trust the client-supplied Content-Type or
# filename extension alone — see ADR discussion in the field-PWA evidence
# audit). No new dependency (python-magic needs a native libmagic install);
# these three signatures are stable, well-documented, and cover the only
# formats this phase supports.
ALLOWED_EVIDENCE_MIME_TYPES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "application/pdf": (b"%PDF-",),
}
EVIDENCE_EXTENSION_BY_MIME = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}

def sniff_evidence_mime(head: bytes) -> str | None:
    for mime, signatures in ALLOWED_EVIDENCE_MIME_TYPES.items():
        if any(head.startswith(sig) for sig in signatures):
            return mime
    return None

def safe_evidence_filename(value: str, extension: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9áéíóúñ]+", "-", normalized).strip("-")[:180] or "evidencia"
    return f"{normalized}.{extension.lower()}"
