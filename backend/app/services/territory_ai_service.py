from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
from time import perf_counter
from uuid import UUID
from pydantic import ValidationError
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.entitlement import AiUsageEvent
from app.models.territory_ai import TerritoryAIConversation,TerritoryAIMessage
from app.models.user import User
from app.schemas.entitlement import FeatureCode
from app.schemas.territory_ai import ProviderStructuredOutput,TerritoryAICitation,TerritoryAIConversationRead,TerritoryAIIntent,TerritoryAIQueryRequest,TerritoryAIResponse
from app.services.campaign_access_service import CampaignAccessService
from app.services.feature_entitlement_service import FeatureEntitlementService
from app.services.security_audit_service import SecurityAuditService
from app.services.territory_ai_intent import TerritoryAIIntentRouter
from app.services.territory_ai_planner import TerritoryAIQueryPlanner
from app.services.territory_ai_policy import TerritoryAIPolicy
from app.services.territory_ai_prompt import TERRITORY_AI_SYSTEM_PROMPT,TERRITORY_AI_SYSTEM_PROMPT_ID,build_user_prompt,provider_documents
from app.services.territory_ai_retrieval import TerritoryAIEvidenceRetriever
from app.services.territory_ai_territory import TerritoryAIResolver,TerritoryAmbiguousError

class TerritoryAiError(Exception):
    def __init__(self,code,message,status_code=403,extra=None):self.code=code;self.message=message;self.status_code=status_code;self.extra=extra or {};super().__init__(message)
@dataclass
class ProviderResult:
    answer:str;model:str;input_tokens:int|None=None;output_tokens:int|None=None;citation_ids:list[str]=field(default_factory=list);limitations:list[str]=field(default_factory=list)
class UnavailableAiProvider:
    name="unavailable";available=False
    def generate(self,question,context):raise RuntimeError("Proveedor no configurado")
_provider=UnavailableAiProvider()
class E2EFakeAiProvider:
    name="fake-e2e";available=True
    def generate(self,question,context):
        if "MALFORMED_E2E" in question:return {"unexpected":True}
        if "TIMEOUT_E2E" in question:raise TimeoutError()
        documents=context.get("documents",[]);kinds=[]
        citation_ids=[]
        for document in documents:
            if document["source_kind"] not in kinds:kinds.append(document["source_kind"]);citation_ids.append(document["evidence_id"])
        current=[d for d in documents if d["source_kind"]=="CNE" and d["title"]=="Padrón electoral actual"]
        projections=[d for d in documents if d["source_kind"]=="TURNOUT_MODEL"]
        if current and projections and "TERRITORY_SUMMARY" not in question:
            registered=sum(d["structured_data"].get("registered_voters") or 0 for d in current)
            expected=sum(d["structured_data"].get("expected_voters_central") or 0 for d in projections)
            projection_register=sum(d["structured_data"].get("registered_voters") or 0 for d in projections)
            rate=(expected/projection_register*100) if projection_register else None
            citation_ids=list(dict.fromkeys(d["evidence_id"] for d in current+projections))
            answer=f"El padrón electoral actual es de {registered:,} electores. La proyección central es de {expected:,} votantes esperados"
            if rate is not None:answer+=f" ({rate:.2f}% del padrón)"
            answer+=". Es una estimación de participación, no de apoyo político."
            return ProviderResult(answer,"territory-ai-fake-v1",10,12,citation_ids,[])
        return ProviderResult("Respuesta grounded sintética. Fuentes disponibles: "+", ".join(kinds)+".","territory-ai-fake-v1",10,12,citation_ids,[])
_e2e_provider=E2EFakeAiProvider()
_LOCAL_FAKE_ENVIRONMENTS={"development","dev","local"}
def get_ai_provider():
    app_env=settings.app_env.strip().lower()
    if app_env=="e2e":return _e2e_provider
    if app_env in _LOCAL_FAKE_ENVIRONMENTS and settings.territory_ai_provider=="fake":return _e2e_provider
    return _provider

class TerritoryAiService:
    ALLOWED_ROLES={"ADMIN","CAMPAIGN_MANAGER","TERRITORIAL_COORDINATOR","ANALYST","CANDIDATE"}
    NO_EVIDENCE="No encontré información suficiente en las fuentes disponibles de Territorio Electoral para responder esa pregunta."
    def __init__(self,db:Session,provider):
        self.db=db;self.provider=provider;self.access=CampaignAccessService(db);self.entitlements=FeatureEntitlementService(db);self.audit=SecurityAuditService(db);self.policy=TerritoryAIPolicy();self.intents=TerritoryAIIntentRouter();self.planner=TerritoryAIQueryPlanner();self.resolver=TerritoryAIResolver(db);self.retriever=TerritoryAIEvidenceRetriever(db)
    def authorize(self,campaign_id,user):
        self.access.require_access(campaign_id,user)
        if not user.is_superuser and not self.ALLOWED_ROLES.intersection(r.code for r in user.roles):raise TerritoryAiError("RBAC_DENIED","Permisos insuficientes")
        entitlement=self.entitlements.get(campaign_id,FeatureCode.TERRITORY_AI);state=self.entitlements.status(entitlement)
        if state not in {"ENABLED","TRIAL"}:
            if state=="EXPIRED" and entitlement.entitlement_type=="TRIAL":self.audit.record("FEATURE_TRIAL_EXPIRED","DENIED","Consulta bloqueada por prueba vencida",user_id=user.id,campaign_id=campaign_id,resource_type="FEATURE_ENTITLEMENT",resource_id=entitlement.id)
            self.db.commit();raise TerritoryAiError("FEATURE_NOT_ENTITLED","Territorio IA no está habilitada para esta campaña")
        if not self.entitlements.quota_available(entitlement):raise TerritoryAiError("AI_QUOTA_EXCEEDED","Cuota de IA agotada",429)
        since=datetime.now(timezone.utc)-timedelta(minutes=1);recent=self.db.scalar(select(func.coalesce(func.sum(AiUsageEvent.request_count),0)).where(AiUsageEvent.campaign_id==campaign_id,AiUsageEvent.user_id==user.id,AiUsageEvent.timestamp>=since)) or 0
        if recent>=settings.territory_ai_rate_limit_per_minute:raise TerritoryAiError("AI_RATE_LIMITED","Demasiadas consultas. Intenta nuevamente en un momento.",429)
        return entitlement
    def _conversation(self,campaign_id,user,data):
        if data.conversation_id:
            c=self.db.get(TerritoryAIConversation,data.conversation_id)
            if not c or c.campaign_id!=campaign_id or c.user_id!=user.id:raise TerritoryAiError("CONVERSATION_NOT_FOUND","Conversación no encontrada",404)
            return c
        c=TerritoryAIConversation(campaign_id=campaign_id,user_id=user.id,title=data.question.strip()[:177]);self.db.add(c);self.db.flush();return c
    def _save(self,conversation,question,response,intent,territory):
        user_message=TerritoryAIMessage(conversation_id=conversation.id,role="USER",content=question,intent=intent.value,territory_id=territory.id if territory else None)
        self.db.add(user_message);self.db.flush();assistant=TerritoryAIMessage(conversation_id=conversation.id,role="ASSISTANT",content=response.answer,citations=[c.model_dump(mode="json") for c in response.citations],intent=intent.value,territory_id=territory.id if territory else None);self.db.add(assistant);conversation.last_intent=intent.value;self.db.flush();return assistant
    def _citation(self,e):return TerritoryAICitation(id=e.evidence_id,source_type=e.source_kind,title=e.title,source_name=e.source_name,reference_date=e.record_date,data_cutoff=e.data_cutoff,territory=e.territory,excerpt=e.excerpt,internal_path=e.internal_path,external_url=e.source_url,freshness=e.freshness)
    def _audit(self,cid,user,intent,territory,evidence,status,started,provider=None,model=None):
        self.audit.record("TERRITORY_AI_QUERY",status,"Consulta de Territorio IA",user_id=user.id,campaign_id=cid,resource_type="TERRITORY_AI",metadata={"intent":intent.value,"territory":territory.name if territory else None,"evidence_types":sorted({e.source_kind.value for e in evidence}),"provider":provider,"model":model,"latency_ms":round((perf_counter()-started)*1000),"status":status})
    def query(self,campaign_id:UUID,data:TerritoryAIQueryRequest|str,user:User):
        if isinstance(data,str):data=TerritoryAIQueryRequest(question=data)
        started=perf_counter();self.authorize(campaign_id,user);conversation=self._conversation(campaign_id,user,data)
        decision=self.policy.evaluate(data.question);previous=TerritoryAIIntent(conversation.last_intent) if conversation.last_intent else None;intents=self.intents.route_all(data.question,previous);intent=intents[0]
        if not decision.allowed:
            response=TerritoryAIResponse(answer=decision.message,citations=[],limitations=[decision.category.value],intent=intent,conversation_id=conversation.id,status="BLOCKED")
            message=self._save(conversation,data.question,response,intent,None);response.message_id=message.id;self._audit(campaign_id,user,intent,None,[],"BLOCKED",started);self.db.commit();return response
        try:territory=self.resolver.resolve(campaign_id,data.question,data.parish_id)
        except TerritoryAmbiguousError as exc:raise TerritoryAiError("TERRITORY_AMBIGUOUS","Se necesita aclarar el territorio",409,{"territories":[x.model_dump() for x in exc.matches]})
        context_ids={k:str(v) for k,v in {"study_id":data.study_id,"activity_id":data.activity_id,"need_id":data.need_id,"public_item_id":data.public_item_id}.items() if v}
        for key,context_intent in (("study_id",TerritoryAIIntent.SURVEY_STUDIES),("activity_id",TerritoryAIIntent.OPERATIONS),("need_id",TerritoryAIIntent.NEEDS),("public_item_id",TerritoryAIIntent.PUBLIC_INTELLIGENCE)):
            if key in context_ids:intent=context_intent;intents=[context_intent];break
        plan=self.planner.plan(intents,territory,context_ids);evidence=self.retriever.retrieve(campaign_id,user,plan,data.question)
        if not evidence:
            response=TerritoryAIResponse(answer=self.NO_EVIDENCE,citations=[],limitations=["EVIDENCE_NOT_AVAILABLE"],intent=intent,territory=territory,conversation_id=conversation.id,status="NO_EVIDENCE");message=self._save(conversation,data.question,response,intent,territory);response.message_id=message.id;self._audit(campaign_id,user,intent,territory,[],"NO_EVIDENCE",started);self.db.commit();return response
        if not getattr(self.provider,"available",False):self.db.rollback();raise TerritoryAiError("AI_PROVIDER_UNAVAILABLE","Territorio IA no está configurada en este entorno.",503)
        try:
            raw=self.provider.generate(build_user_prompt(data.question,plan),{"system_prompt_id":TERRITORY_AI_SYSTEM_PROMPT_ID,"system_prompt":TERRITORY_AI_SYSTEM_PROMPT,"documents":provider_documents(evidence)})
        except (TimeoutError,):self.db.rollback();raise TerritoryAiError("AI_PROVIDER_TIMEOUT","El proveedor de IA no respondió a tiempo.",504)
        except Exception:self.db.rollback();raise TerritoryAiError("AI_PROVIDER_ERROR","No fue posible completar la consulta de IA.",502)
        try:
            payload={"answer":raw.answer,"citation_ids":getattr(raw,"citation_ids",[]),"limitations":getattr(raw,"limitations",[])} if hasattr(raw,"answer") else raw
            output=ProviderStructuredOutput.model_validate(payload)
        except (ValidationError,TypeError,ValueError):self.db.rollback();raise TerritoryAiError("AI_PROVIDER_INVALID_RESPONSE","El proveedor devolvió una respuesta inválida.",502)
        if self.policy.SECRET.search(output.answer):self.db.rollback();raise TerritoryAiError("AI_PROVIDER_INVALID_RESPONSE","El proveedor devolvió contenido no permitido.",502)
        available={e.evidence_id:e for e in evidence};valid_ids=list(dict.fromkeys(i for i in output.citation_ids if i in available));citations=[self._citation(available[i]) for i in valid_ids]
        found={e.source_kind for e in evidence};missing=[kind.value for kind in plan.source_kinds if kind not in found];limitations=list(dict.fromkeys(output.limitations+(["Sin evidencia disponible para: "+", ".join(missing)] if missing else [])))
        model=getattr(raw,"model","unknown");response=TerritoryAIResponse(answer=output.answer,citations=citations,limitations=limitations,intent=intent,territory=territory,conversation_id=conversation.id,provider=self.provider.name,model=model)
        message=self._save(conversation,data.question,response,intent,territory);response.message_id=message.id;usage=AiUsageEvent(campaign_id=campaign_id,user_id=user.id,provider=self.provider.name,model=model,input_tokens=getattr(raw,"input_tokens",None),output_tokens=getattr(raw,"output_tokens",None),request_count=1);self.db.add(usage);self._audit(campaign_id,user,intent,territory,evidence,"SUCCESS",started,self.provider.name,model);self.db.commit();return response
    def list_conversations(self,campaign_id,user):
        self.access.require_access(campaign_id,user);return list(self.db.scalars(select(TerritoryAIConversation).where(TerritoryAIConversation.campaign_id==campaign_id,TerritoryAIConversation.user_id==user.id).order_by(TerritoryAIConversation.updated_at.desc())))
    def conversation(self,campaign_id,conversation_id,user):
        self.access.require_access(campaign_id,user);obj=self.db.get(TerritoryAIConversation,conversation_id)
        if not obj or obj.campaign_id!=campaign_id or obj.user_id!=user.id:raise TerritoryAiError("CONVERSATION_NOT_FOUND","Conversación no encontrada",404)
        return obj
