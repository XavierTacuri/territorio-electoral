import hashlib
import os
import shutil
from abc import ABC,abstractmethod
from pathlib import Path
from uuid import uuid4

class ReportStorage(ABC):
    @abstractmethod
    def store(self,source:Path,extension:str):...
    @abstractmethod
    def resolve(self,key:str)->Path:...
    @abstractmethod
    def delete(self,key:str)->bool:...

class LocalReportStorage(ReportStorage):
    def __init__(self,root:str,max_file_mb:int=50):
        if not root.strip():raise ValueError("REPORT_OUTPUT_DIR no puede estar vacío")
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.max_bytes=max_file_mb*1024*1024
    def resolve(self,key:str)->Path:
        if Path(key).is_absolute() or ".." in Path(key).parts:raise ValueError("Ruta de artefacto insegura")
        raw=self.root/key
        if raw.is_symlink():raise ValueError("Ruta de artefacto insegura")
        target=raw.resolve(strict=False)
        if target.parent!=self.root:raise ValueError("Ruta de artefacto insegura")
        return target
    def store(self,source:Path,extension:str):
        size=source.stat().st_size
        if size>self.max_bytes:raise ValueError("El informe supera el tamaño permitido")
        key=f"{uuid4().hex}.{extension.lower()}";target=self.resolve(key)
        shutil.move(str(source),target);digest=hashlib.sha256(target.read_bytes()).hexdigest()
        return key,size,digest
    def delete(self,key:str)->bool:
        target=self.resolve(key)
        if not target.exists():return False
        if target.is_symlink():raise ValueError("Ruta de artefacto insegura")
        target.unlink();return True
