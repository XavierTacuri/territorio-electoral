import pytest

from app.services.artifact_storage import LocalArtifactDownload, LocalArtifactStorage


def test_store_delete_exists_round_trip(tmp_path):
    storage = LocalArtifactStorage(str(tmp_path), max_file_mb=1)
    source = tmp_path / "in.pdf"
    source.write_bytes(b"hello-report")
    key, size, digest = storage.store(source, "pdf")
    assert size == len(b"hello-report") and len(digest) == 64
    assert storage.exists(key) is True
    assert storage.delete(key) is True
    assert storage.exists(key) is False
    assert storage.delete(key) is False


def test_download_wraps_resolved_path(tmp_path):
    storage = LocalArtifactStorage(str(tmp_path), max_file_mb=1)
    source = tmp_path / "in.jpg"
    source.write_bytes(b"jpeg-bytes")
    key, *_ = storage.store(source, "jpg")
    download = storage.download(key, filename="acta.jpg", content_type="image/jpeg")
    assert isinstance(download, LocalArtifactDownload)
    assert download.path == storage.resolve(key)
    assert download.path.read_bytes() == b"jpeg-bytes"


def test_download_ignores_filename_and_content_type_hints_safely(tmp_path):
    # Local backend doesn't need Response-Content-* params (FastAPI's
    # FileResponse sets headers directly) — passing them must never raise.
    storage = LocalArtifactStorage(str(tmp_path), max_file_mb=1)
    source = tmp_path / "in.jpg"
    source.write_bytes(b"jpeg-bytes")
    key, *_ = storage.store(source, "jpg")
    storage.download(key)
    storage.download(key, filename=None, content_type=None)


def test_resolve_rejects_path_traversal(tmp_path):
    storage = LocalArtifactStorage(str(tmp_path), max_file_mb=1)
    with pytest.raises(ValueError):
        storage.resolve("../outside.pdf")


def test_store_rejects_oversized_file(tmp_path):
    storage = LocalArtifactStorage(str(tmp_path), max_file_mb=0)
    source = tmp_path / "in.jpg"
    source.write_bytes(b"x" * 10)
    with pytest.raises(ValueError):
        storage.store(source, "jpg")
