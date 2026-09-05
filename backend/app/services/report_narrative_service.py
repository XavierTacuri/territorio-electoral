"""Redacción grounded para el Centro de Informes.

Territorio IA no arma el informe ni recalcula cifras: recibe hechos ya
extraídos por el backend (los mismos "facts" usados para las tablas del PDF)
y únicamente redacta un resumen ejecutivo y hallazgos descriptivos a partir de
ellos. Si no hay proveedor disponible, o si la salida no puede validarse, cae
en un renderer determinístico basado en los mismos hechos — el flujo de
informes nunca se interrumpe por falta de IA.
"""
import logging
import re

from app.schemas.reports import ReportNarrativeRead
from app.services.territory_ai_service import get_ai_provider

logger = logging.getLogger("territorio.reports")

REPORT_NARRATIVE_SYSTEM_PROMPT = """Eres un redactor grounded para el Centro de Informes de Territorio Electoral.
Recibes hechos ya extraídos y verificados por el backend (nunca accedes a la base de datos ni recalculas cifras).
Tu única tarea es redactar, en español neutro y profesional, un resumen ejecutivo y una lista de hallazgos descriptivos que resuman esos hechos.
No inventes cifras, fechas, nombres ni fuentes que no estén en los hechos entregados.
No generes persuasión política, microtargeting, perfiles individuales, predicción de ganador, puntajes de apoyo/oscilación (support/swing scores) ni rankings para atacar o priorizar territorios.
Si los hechos incluyen datos marcados como demo (simulados para demostración), menciónalo explícitamente y no los presentes como oficiales.
Responde exclusivamente como JSON con answer, citation_ids y limitations. En "answer" usa exactamente este formato:
RESUMEN:
<párrafo de resumen ejecutivo, 3 a 6 oraciones>

HALLAZGOS:
- <hallazgo 1>
- <hallazgo 2>
- <hallazgo 3>
Cita los evidence_id de los hechos que uses. Si la evidencia es insuficiente para alguna sección, dilo en limitations."""


def _deterministic(report_kind_label: str, summary_text: str | None, bullets: list[str], is_demo: bool) -> ReportNarrativeRead:
    resumen = summary_text or f"{report_kind_label} generado a partir de los datos disponibles en el sistema."
    if is_demo:
        resumen += " Este informe incorpora datos simulados para demostración."
    hallazgos = bullets[:8] or ["No hay suficientes datos para identificar hallazgos en este período."]
    return ReportNarrativeRead(
        titulo_sugerido=report_kind_label,
        resumen_ejecutivo=resumen,
        hallazgos_principales=hallazgos,
        limitations=["Redacción determinística: proveedor de IA no disponible en este momento."],
        provider="deterministic-fallback",
    )


def _parse_answer(answer: str) -> tuple[str, list[str]] | None:
    resumen_match = re.search(r"RESUMEN:\s*(.+?)(?:\n\s*HALLAZGOS:|\Z)", answer, re.DOTALL | re.IGNORECASE)
    hallazgos_match = re.search(r"HALLAZGOS:\s*(.+)", answer, re.DOTALL | re.IGNORECASE)
    if not resumen_match or not hallazgos_match:
        return None
    resumen = resumen_match.group(1).strip()
    bullets = [line.strip(" -\t") for line in hallazgos_match.group(1).strip().splitlines() if line.strip(" -\t")]
    if not resumen or not bullets:
        return None
    return resumen, bullets


class ReportNarrativeService:
    def __init__(self, provider=None):
        self.provider = provider if provider is not None else get_ai_provider()

    def synthesize(self, report_kind_label: str, documents: list[dict], summary_text: str | None,
                   fallback_bullets: list[str], is_demo: bool) -> ReportNarrativeRead:
        if not documents or getattr(self.provider, "name", None) == "fake-e2e" or not getattr(self.provider, "available", False):
            return _deterministic(report_kind_label, summary_text, fallback_bullets, is_demo)
        try:
            context = {"system_prompt": REPORT_NARRATIVE_SYSTEM_PROMPT, "documents": documents}
            raw = self.provider.generate(
                f"Redacta el resumen ejecutivo y los hallazgos de: {report_kind_label}.", context,
            )
            answer = getattr(raw, "answer", None) if hasattr(raw, "answer") else (raw or {}).get("answer")
            parsed = _parse_answer(answer or "")
            if parsed is None:
                return _deterministic(report_kind_label, summary_text, fallback_bullets, is_demo)
            resumen, bullets = parsed
            limitations = list(getattr(raw, "limitations", None) or [])
            if is_demo and not any("demo" in l.lower() or "simulad" in l.lower() for l in limitations + [resumen]):
                limitations.append("Este informe incorpora datos simulados para demostración.")
            return ReportNarrativeRead(
                titulo_sugerido=report_kind_label,
                resumen_ejecutivo=resumen,
                hallazgos_principales=bullets[:8],
                limitations=limitations,
                provider=getattr(self.provider, "name", "unknown"),
            )
        except Exception as exc:  # noqa: BLE001 — nunca romper el flujo de informes por falla del proveedor
            logger.warning("report_narrative_provider_error", extra={"error_type": type(exc).__name__})
            return _deterministic(report_kind_label, summary_text, fallback_bullets, is_demo)
