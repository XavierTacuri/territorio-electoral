import hashlib
import shutil
from abc import ABC,abstractmethod
from pathlib import Path
from uuid import uuid4

class EvidenceStorage(ABC):
    """Storage abstraction for uploaded activity evidence files.

    Mirrors ReportStorage/LocalReportStorage (report_storage_service.py) so
    the codebase has one storage pattern, not two. LocalEvidenceStorage is
    what development and the isolated E2E stack use; a production deployment
    swaps in an object-storage-backed implementation of this same interface
    (e.g. S3-compatible) without touching the service or route layer.
    """
    @abstractmethod
    def store(self,source:Path,extension:str):...
    @abstractmethod
    def resolve(self,key:str)->Path:...
    @abstractmethod
    def delete(self,key:str)->bool:...

class LocalEvidenceStorage(EvidenceStorage):
    def __init__(self,root:str,max_file_mb:int=15):
        if not root.strip():raise ValueError("EVIDENCE_OUTPUT_DIR no puede estar vacío")
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.max_bytes=max_file_mb*1024*1024
    def resolve(self,key:str)->Path:
        if Path(key).is_absolute() or ".." in Path(key).parts:raise ValueError("Ruta de evidencia insegura")
        raw=self.root/key
        if raw.is_symlink():raise ValueError("Ruta de evidencia insegura")
        target=raw.resolve(strict=False)
        if target.parent!=self.root:raise ValueError("Ruta de evidencia insegura")
        return target
    def store(self,source:Path,extension:str):
        size=source.stat().st_size
        if size>self.max_bytes:raise ValueError("El archivo supera el tamaño permitido")
        key=f"{uuid4().hex}.{extension.lower()}";target=self.resolve(key)
        shutil.move(str(source),target);digest=hashlib.sha256(target.read_bytes()).hexdigest()
        return key,size,digest
    def delete(self,key:str)->bool:
        target=self.resolve(key)
        if not target.exists():return False
        if target.is_symlink():raise ValueError("Ruta de evidencia insegura")
        target.unlink();return True
