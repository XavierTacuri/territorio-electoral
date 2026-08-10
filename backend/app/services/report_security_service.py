import re

def safe_download_name(value: str, extension: str) -> str:
    normalized=value.lower().strip()
    normalized=re.sub(r"[^a-z0-9áéíóúñ]+","-",normalized).strip("-")[:180] or "informe"
    return f"{normalized}.{extension.lower()}"
