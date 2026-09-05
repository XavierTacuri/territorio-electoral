"""Verificador de afirmaciones del Asistente de Debate (§44-46 de Fase Final).

Nunca decide un LLM si una afirmación es verdadera: el veredicto surge de
comparar de forma determinística los números y palabras clave de la
afirmación contra la evidencia ya autorizada que recupera Territorio IA. El
resultado es siempre uno de tres niveles de respaldo — nunca VERDADERO/FALSO —
porque la evidencia disponible puede ser insuficiente para una conclusión
binaria.
"""
import re
from datetime import datetime

from app.schemas.debate import ClaimCheckResponse, ClaimEvidenceItem
from app.schemas.territory_ai import TerritoryAIIntent
from app.services.campaign_access_service import CampaignAccessService
from app.services.security_audit_service import SecurityAuditService
from app.services.territory_ai_planner import TerritoryAIQueryPlanner
from app.services.territory_ai_policy import TerritoryAIPolicy
from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
from app.services.territory_ai_territory import TerritoryAIResolver, TerritoryAmbiguousError

SOURCE_LABELS = {"OFFICIAL": "Oficial", "PUBLIC": "Fuente pública", "CAMPAIGN": "Registro de campaña", "DEMO": "Datos simulados"}
NO_EVIDENCE_WARNING = "No existe información suficiente en el sistema para responder esta afirmación."
STOPWORDS = {"que", "hay", "con", "los", "las", "del", "por", "para", "una", "uno", "son", "este", "esta", "esa", "ese", "hacia", "desde", "sobre", "hasta", "hoy", "hace", "hab"}
NUMBER_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?:\s?%)?|\d+(?:[.,]\d+)?(?:\s?%)?")


def _parse_number(token: str):
    token = token.strip()
    is_percent = token.endswith("%")
    core = token[:-1].strip() if is_percent else token
    if "." in core and "," in core:
        core = core.replace(".", "").replace(",", ".")
    elif core.count(".") > 1:
        core = core.replace(".", "")
    elif "." in core:
        head, _, tail = core.rpartition(".")
        if head and len(tail) == 3:
            core = core.replace(".", "")
    elif "," in core:
        core = core.replace(",", ".")
    try:
        return float(core), is_percent
    except ValueError:
        return None


def extract_claim_numbers(text: str) -> list[tuple[float, bool]]:
    out = []
    for match in NUMBER_RE.finditer(text):
        parsed = _parse_number(match.group())
        if parsed is not None:
            out.append(parsed)
    return out


def extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[a-záéíóúñ]{4,}", text.casefold())
    return [w for w in words if w not in STOPWORDS]


def _comparable(value, field_name: str):
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    field = field_name.lower()
    if ("rate" in field or "percentage" in field or "percent" in field) and -1 <= value <= 1:
        return round(value * 100, 2)
    return round(float(value), 2)


def _numbers_match(claim_value: float, comparable: float | None) -> bool:
    if comparable is None:
        return False
    tolerance = max(0.5, abs(comparable) * 0.01)
    return abs(claim_value - comparable) <= tolerance


class ClaimVerificationService:
    ALLOWED_ROLES = {"ADMIN", "CAMPAIGN_MANAGER", "TERRITORIAL_COORDINATOR", "ANALYST", "CANDIDATE"}

    def __init__(self, db):
        self.db = db
        self.access = CampaignAccessService(db)
        self.policy = TerritoryAIPolicy()
        self.planner = TerritoryAIQueryPlanner()
        self.resolver = TerritoryAIResolver(db)
        self.retriever = TerritoryAIEvidenceRetriever(db)
        self.audit = SecurityAuditService(db)

    def authorize(self, campaign_id, user):
        self.access.require_access(campaign_id, user)
        if not user.is_superuser and not self.ALLOWED_ROLES.intersection(r.code for r in user.roles):
            raise PermissionError("Permisos insuficientes")

    def check(self, campaign_id, request, user) -> ClaimCheckResponse:
        self.authorize(campaign_id, user)
        decision = self.policy.evaluate(request.claim_text)
        if not decision.allowed:
            self.audit.record("CLAIM_CHECKED", "BLOCKED", "Verificación de afirmación bloqueada", user_id=user.id, campaign_id=campaign_id,
                               resource_type="CLAIM_CHECK", metadata={"category": decision.category.value})
            self.db.commit()
            return ClaimCheckResponse(claim_text=request.claim_text, verdict="UNSUPPORTED",
                                       verdict_label="NO RESPALDADA CON LA EVIDENCIA DISPONIBLE", evidence=[], warnings=[decision.message])
        try:
            territory = self.resolver.resolve(campaign_id, request.claim_text, request.parish_id)
        except TerritoryAmbiguousError:
            territory = None
        plan = self.planner.plan(TerritoryAIIntent.DEBATE_BRIEF, territory)
        evidence = self.retriever.retrieve(campaign_id, user, plan, request.claim_text)
        numbers = extract_claim_numbers(request.claim_text)
        keywords = extract_keywords(request.claim_text)
        distinct_numbers = {n for n, _ in numbers}
        matched, matched_numbers = [], set()
        for item in evidence:
            hit = False
            for field, value in item.structured_data.items():
                comparable = _comparable(value, field)
                if comparable is None:
                    continue
                for claim_value, _ in numbers:
                    if _numbers_match(claim_value, comparable):
                        matched_numbers.add(claim_value)
                        hit = True
            haystack = f"{item.title} {item.excerpt or ''}".casefold()
            if any(kw in haystack for kw in keywords):
                hit = True
            if hit:
                matched.append(item)
        if numbers:
            if matched_numbers == distinct_numbers and matched:
                verdict, label = "SUPPORTED", "RESPALDADA"
            elif matched_numbers:
                verdict, label = "PARTIALLY_SUPPORTED", "PARCIALMENTE RESPALDADA"
            else:
                verdict, label = "UNSUPPORTED", "NO RESPALDADA CON LA EVIDENCIA DISPONIBLE"
        elif matched:
            verdict, label = ("SUPPORTED", "RESPALDADA") if len(matched) >= 2 else ("PARTIALLY_SUPPORTED", "PARCIALMENTE RESPALDADA")
        else:
            verdict, label = "UNSUPPORTED", "NO RESPALDADA CON LA EVIDENCIA DISPONIBLE"
        warnings = []
        for item in matched:
            year = item.structured_data.get("reference_year") or item.structured_data.get("year")
            if year:
                warnings.append(f"El dato corresponde al año {year}.")
        if not matched:
            warnings.append(NO_EVIDENCE_WARNING)
        shown = matched or evidence[:3]
        items = [ClaimEvidenceItem(
            id=item.evidence_id, title=item.title, source_name=item.source_name, evidence_class=item.evidence_class,
            source_label=SOURCE_LABELS.get(item.evidence_class, item.evidence_class),
            record_date=item.record_date.date() if isinstance(item.record_date, datetime) else item.record_date,
            external_url=item.source_url,
        ) for item in shown]
        self.audit.record("CLAIM_CHECKED", "SUCCESS", "Verificación de afirmación", user_id=user.id, campaign_id=campaign_id,
                           resource_type="CLAIM_CHECK", metadata={"verdict": verdict, "evidence_count": len(items)})
        self.db.commit()
        return ClaimCheckResponse(claim_text=request.claim_text, verdict=verdict, verdict_label=label, evidence=items,
                                   warnings=list(dict.fromkeys(warnings)))
