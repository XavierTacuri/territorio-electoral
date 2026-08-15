from datetime import datetime,timedelta,timezone
from math import ceil
from urllib.parse import urlsplit,urlunsplit
from uuid import UUID
import time
import hashlib
import re
import httpx
from sqlalchemy import delete,func,or_,select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.operational import CitizenNeed
from app.models.alerts import AlertRule,OperationalAlert
from app.models.public_intelligence import *
from app.models.territory import Parish
from app.schemas.public_intelligence import *
from app.services.campaign_access_service import CampaignAccessService
from app.services.exceptions import BusinessRuleError,NotFoundError
from app.services.public_fetch_security import validate_public_url,validate_redirect
from app.services.public_source_adapters import JsonApiAdapter,RSSAdapter
from app.services.security_audit_service import SecurityAuditService

def utcnow():return datetime.now(timezone.utc)
def canonical(url):
    p=urlsplit(url);return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/") or "/",p.query,""))
STALE_TOLERANCE_RATIO=.25 # proportional scheduler-jitter tolerance
class PublicIntelligenceService:
    def __init__(self,db:Session,http_client=None):self.db=db;self.access=CampaignAccessService(db);self.audit=SecurityAuditService(db);self.http_client=http_client
    def manage(self,cid,user):return self.access.require_management(cid,user)
    def source(self,sid):
        obj=self.db.get(PublicSource,sid)
        if not obj:raise NotFoundError("Fuente pública no encontrada")
        return obj
    def create_source(self,cid,user,data):
        self.manage(cid,user)
        for url in (data.base_url,data.feed_url,data.api_url):
            if url:validate_public_url(url)
        obj=PublicSource(campaign_id=cid,**data.model_dump(mode="json"));self.db.add(obj);self.db.flush();self.audit.record("source_created","SUCCESS","Fuente pública creada",user_id=user.id,campaign_id=cid,resource_type="PUBLIC_SOURCE",resource_id=obj.id);self.db.commit();self.db.refresh(obj);return obj
    def update_source(self,sid,user,data):
        obj=self.source(sid);self.manage(obj.campaign_id,user);was_active=obj.active
        values=data.model_dump(exclude_unset=True,mode="json")
        for key in ("base_url","feed_url","api_url"):
            if values.get(key):validate_public_url(values[key])
        for k,v in values.items():setattr(obj,k,v)
        event="source_disabled" if values.get("active") is False else "source_reactivated" if values.get("active") is True and not was_active else "source_updated";self.audit.record(event,"SUCCESS","Fuente pública actualizada",user_id=user.id,campaign_id=obj.campaign_id,resource_type="PUBLIC_SOURCE",resource_id=obj.id);self.db.commit();self.db.refresh(obj);return obj
    def sources(self,cid,user):self.access.require_access(cid,user);return list(self.db.scalars(select(PublicSource).where(PublicSource.campaign_id==cid).order_by(PublicSource.name)))
    def _get(self,client,url,headers):
        current=validate_public_url(url);attempt=0
        while True:
            response=client.get(current,headers=headers,follow_redirects=False)
            if response.status_code in {301,302,303,307,308}:
                current=validate_redirect(current,response.headers.get("location", ""));continue
            if response.status_code in {429,502,503,504} and attempt<2:
                attempt+=1;time.sleep(min(float(response.headers.get("Retry-After","0") or 0),2) or .1*2**attempt);continue
            response.raise_for_status()
            if len(response.content)>settings.public_fetch_max_bytes:raise BusinessRuleError("Respuesta excede el tamaño permitido")
            return response
    def fetch(self,sid,user,trigger="MANUAL"):
        source=self.source(sid);self.manage(source.campaign_id,user)
        if not source.active:raise BusinessRuleError("La fuente está inactiva")
        run=PublicSourceFetchRun(source_id=sid,started_at=utcnow(),status="RUNNING",trigger_type=trigger);self.db.add(run);self.db.flush();source.last_fetch_at=run.started_at
        try:
            url=source.feed_url if source.retrieval_method=="RSS" else source.api_url if source.retrieval_method=="API" else source.base_url
            if source.retrieval_method=="MANUAL":raise BusinessRuleError("Las fuentes manuales no admiten actualización automática")
            headers={"User-Agent":settings.public_fetch_user_agent,"Accept":"application/rss+xml, application/atom+xml, application/json, text/xml;q=0.9"}
            if source.etag:headers["If-None-Match"]=source.etag
            if source.last_modified:headers["If-Modified-Since"]=source.last_modified
            own=self.http_client is None;client=self.http_client or httpx.Client(timeout=settings.public_fetch_timeout_seconds)
            try:response=self._get(client,url,headers)
            finally:
                if own:client.close()
            adapter=RSSAdapter() if source.retrieval_method=="RSS" else JsonApiAdapter(source.adapter_config)
            normalized=adapter.normalize(response.content,url);run.items_discovered=len(normalized)
            for found in normalized:
                try:self._upsert(source,found,run)
                except Exception:run.items_failed+=1
            source.etag=response.headers.get("etag");source.last_modified=response.headers.get("last-modified");source.last_success_at=utcnow();source.consecutive_failures=0;source.items_last_fetch=run.items_created+run.items_updated;run.status="PARTIAL" if run.items_failed else "SUCCESS";self._resolve_stale(source)
            if run.items_created and source.official:self._alert(source,"NEW_OFFICIAL_PUBLICATION","Nueva publicación oficial",f"{run.items_created} publicaciones oficiales nuevas.")
            if run.items_updated:self._alert(source,"PUBLIC_DOCUMENT_UPDATED","Documento público actualizado",f"{run.items_updated} publicaciones registran una revisión.")
        except Exception as exc:
            source.consecutive_failures+=1;run.status="FAILED";run.error_summary=re.sub(r"([?&](?:token|api[_-]?key|password|authorization|cookie)=)[^&\\s]+",r"\1[OCULTO]",str(exc),flags=re.I)[:1000];self._alert(source,"SOURCE_FETCH_FAILED","Error de actualización de fuente",f"No fue posible actualizar {source.name}.");self.audit.record("fetch_failed","FAILED","Actualización de fuente pública fallida",user_id=user.id,campaign_id=source.campaign_id,resource_type="PUBLIC_SOURCE",resource_id=source.id)
        run.finished_at=utcnow();self.audit.record("manual_fetch",run.status,"Actualización manual de fuente pública",user_id=user.id,campaign_id=source.campaign_id,resource_type="PUBLIC_SOURCE",resource_id=source.id,metadata={"created":run.items_created,"updated":run.items_updated,"unchanged":run.items_unchanged});self.db.commit();self.db.refresh(run);return run
    def _alert(self,source,code,title,message):
        rule=self.db.scalar(select(AlertRule).where(AlertRule.code==code,AlertRule.is_active.is_(True)))
        if not rule:return
        fingerprint=hashlib.sha256(f"{source.campaign_id}:{source.id}:{code}:{utcnow().date()}".encode()).hexdigest()
        if not self.db.scalar(select(OperationalAlert.id).where(OperationalAlert.campaign_id==source.campaign_id,OperationalAlert.fingerprint==fingerprint)):
            self.db.add(OperationalAlert(alert_rule_id=rule.id,campaign_id=source.campaign_id,severity=rule.default_severity,status="OPEN",title=title,message=message,detected_date=utcnow().date(),last_seen_date=utcnow().date(),resource_type="PUBLIC_SOURCE",resource_id=source.id,fingerprint=fingerprint,evidence={"source_name":source.name}))
    def freshness(self,source,now=None):
        now=now or utcnow()
        if not source.active:return ("INACTIVE",None,None)
        if not source.last_success_at:return ("NEVER",None,None)
        if not source.refresh_interval_minutes:return ("CURRENT",None,None)
        interval=timedelta(minutes=source.refresh_interval_minutes);next_at=source.last_success_at+interval;stale_at=next_at+interval*STALE_TOLERANCE_RATIO
        return ("STALE" if now>stale_at else "CURRENT",next_at,stale_at)
    def _stale_fingerprint(self,source):return hashlib.sha256(f"{source.campaign_id}:{source.id}:SOURCE_STALE".encode()).hexdigest()
    def _resolve_stale(self,source,now=None):
        now=now or utcnow();alert=self.db.scalar(select(OperationalAlert).where(OperationalAlert.campaign_id==source.campaign_id,OperationalAlert.fingerprint==self._stale_fingerprint(source),OperationalAlert.status.in_(["OPEN","ACKNOWLEDGED"])))
        if alert:alert.status="RESOLVED";alert.is_active=False;alert.resolved_date=now.date();alert.last_seen_date=now.date()
    def evaluate_stale_sources(self,cid,user,now=None):
        self.manage(cid,user);now=now or utcnow();created=0
        for source in self.db.scalars(select(PublicSource).where(PublicSource.campaign_id==cid)):
            status,_,stale_at=self.freshness(source,now);fp=self._stale_fingerprint(source)
            if status!="STALE":self._resolve_stale(source,now);continue
            rule=self.db.scalar(select(AlertRule).where(AlertRule.code=="SOURCE_STALE",AlertRule.is_active.is_(True)))
            if not rule:continue
            alert=self.db.scalar(select(OperationalAlert).where(OperationalAlert.campaign_id==cid,OperationalAlert.fingerprint==fp))
            if alert:alert.status="OPEN";alert.is_active=True;alert.resolved_date=None;alert.last_seen_date=now.date()
            else:self.db.add(OperationalAlert(alert_rule_id=rule.id,campaign_id=cid,severity=rule.default_severity,status="OPEN",title="Fuente pública desactualizada",message=f"{source.name} superó su intervalo de actualización.",detected_date=now.date(),last_seen_date=now.date(),resource_type="PUBLIC_SOURCE",resource_id=source.id,fingerprint=fp,evidence={"source_name":source.name,"stale_after_at":stale_at.isoformat()}));created+=1
        self.db.commit();return {"created":created}
    def map_metrics(self,cid,user,period="30",topic=None):
        campaign=self.access.require_access(cid,user);since=None if period=="total" else utcnow()-timedelta(days=int(period));parishes=list(self.db.scalars(select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True)).order_by(Parish.dpa_code)))
        q=select(PublicItemTerritory.parish_id,func.count(func.distinct(PublicIntelligenceItem.id))).join(PublicIntelligenceItem).join(PublicSource).where(PublicSource.campaign_id==cid)
        if since:q=q.where(PublicIntelligenceItem.published_at>=since)
        if topic:q=q.join(PublicItemTopic,PublicItemTopic.item_id==PublicIntelligenceItem.id).join(PublicTopic).where(PublicTopic.code==topic)
        counts=dict(self.db.execute(q.group_by(PublicItemTerritory.parish_id)).all());return [MapMetricRead(parish_id=p.id,dpa_code=p.dpa_code,name=p.name,value=counts.get(p.id,0)) for p in parishes]
    def _upsert(self,source,found,run):
        url=canonical(found.url);item=self.db.scalar(select(PublicIntelligenceItem).where(PublicIntelligenceItem.source_id==source.id,or_(PublicIntelligenceItem.canonical_url==url,PublicIntelligenceItem.external_id==found.external_id if found.external_id else False)))
        now=utcnow();meta=found.metadata or {}
        if not item:
            item=PublicIntelligenceItem(source_id=source.id,external_id=found.external_id,title=found.title,summary=found.summary,item_type=found.item_type,url=found.url,canonical_url=url,published_at=found.published_at,fetched_at=now,author=found.author,content_excerpt=found.excerpt,normalized_text=found.excerpt,content_hash=found.content_hash,original_metadata=meta);self.db.add(item);self.db.flush();self.db.add(PublicItemRevision(item_id=item.id,content_hash=found.content_hash,fetched_at=now,change_detected=False,metadata_snapshot=meta));run.items_created+=1;self._classify(source,item)
        elif item.content_hash!=found.content_hash:
            item.title=found.title;item.summary=found.summary;item.content_excerpt=found.excerpt;item.normalized_text=found.excerpt;item.published_at=found.published_at;item.fetched_at=now;item.content_hash=found.content_hash;item.original_metadata=meta;self.db.add(PublicItemRevision(item_id=item.id,content_hash=found.content_hash,fetched_at=now,change_detected=True,metadata_snapshot=meta));run.items_updated+=1;self._classify(source,item)
        else:item.fetched_at=now;run.items_unchanged+=1
    def _classify(self,source,item):
        self.db.execute(delete(PublicItemTopic).where(PublicItemTopic.item_id==item.id));self.db.execute(delete(PublicItemTerritory).where(PublicItemTerritory.item_id==item.id))
        text=f"{item.title} {item.summary or ''}".casefold()
        for topic in self.db.scalars(select(PublicTopic).where(PublicTopic.active.is_(True))):
            if any(k.casefold() in text for k in topic.keywords):self.db.add(PublicItemTopic(item_id=item.id,topic_id=topic.id,association_method="KEYWORD"))
        campaign=self.access.require_access(source.campaign_id,type("U",(),{"is_superuser":True,"roles":[]})())
        for parish in self.db.scalars(select(Parish).where(Parish.canton_id==campaign.canton_id,Parish.is_active.is_(True))):
            if parish.name.casefold() in text:self.db.add(PublicItemTerritory(item_id=item.id,territory_level="PARISH",parish_id=parish.id,association_method="TEXT_MATCH",confidence=.9))
    def _read(self,item):
        source=self.source(item.source_id);topics=[{"code":t.code,"name":t.name} for t in self.db.scalars(select(PublicTopic).join(PublicItemTopic,PublicItemTopic.topic_id==PublicTopic.id).where(PublicItemTopic.item_id==item.id))];territories=[{"parish_id":p.id,"name":p.name,"association_method":link.association_method,"confidence":link.confidence} for link,p in self.db.execute(select(PublicItemTerritory,Parish).join(Parish,Parish.id==PublicItemTerritory.parish_id).where(PublicItemTerritory.item_id==item.id))];revisions=[{"fetched_at":r.fetched_at,"change_detected":r.change_detected,"content_hash":r.content_hash} for r in self.db.scalars(select(PublicItemRevision).where(PublicItemRevision.item_id==item.id).order_by(PublicItemRevision.fetched_at.desc()))];return ItemRead(id=item.id,source_id=source.id,source_name=source.name,source_url=source.base_url,publisher=source.publisher,official=source.official,title=item.title,summary=item.summary,item_type=item.item_type,url=item.url,canonical_url=item.canonical_url,published_at=item.published_at,fetched_at=item.fetched_at,author=item.author,content_excerpt=item.content_excerpt,language=item.language,content_hash=item.content_hash,status=item.status,topics=topics,territories=territories,revisions=revisions)
    def items(self,cid,user,page,page_size,search=None,source_id=None,topic=None,parish_id=None,date_from=None,date_to=None,official=None):
        self.access.require_access(cid,user);q=select(PublicIntelligenceItem).join(PublicSource).where(PublicSource.campaign_id==cid)
        assignments=self.access.territorial_ids(cid,user)
        if assignments is not None:
            parish_ids={x.parish_id for x in assignments};q=q.where(PublicIntelligenceItem.id.in_(select(PublicItemTerritory.item_id).where(PublicItemTerritory.parish_id.in_(parish_ids))) if parish_ids else False)
        if search:
            topic_match = select(PublicItemTopic.item_id).join(
                PublicTopic, PublicTopic.id == PublicItemTopic.topic_id
            ).where(
                PublicItemTopic.item_id == PublicIntelligenceItem.id,
                or_(
                    PublicTopic.code.ilike(f"%{search}%"),
                    PublicTopic.name.ilike(f"%{search}%"),
                ),
            )
            q=q.where(or_(PublicIntelligenceItem.title.ilike(f"%{search}%"),PublicIntelligenceItem.summary.ilike(f"%{search}%"),PublicSource.publisher.ilike(f"%{search}%"),topic_match.exists()))
        if source_id:q=q.where(PublicSource.id==source_id)
        if official is not None:q=q.where(PublicSource.official==official)
        if date_from:q=q.where(PublicIntelligenceItem.published_at>=date_from)
        if date_to:q=q.where(PublicIntelligenceItem.published_at<date_to+timedelta(days=1))
        if topic:q=q.join(PublicItemTopic).join(PublicTopic).where(PublicTopic.code==topic)
        if parish_id:q=q.where(PublicIntelligenceItem.id.in_(select(PublicItemTerritory.item_id).where(PublicItemTerritory.parish_id==parish_id)))
        q=q.distinct()
        count=self.db.scalar(select(func.count()).select_from(q.subquery())) or 0;rows=self.db.scalars(q.order_by(PublicIntelligenceItem.published_at.desc().nullslast(),PublicIntelligenceItem.fetched_at.desc()).offset((page-1)*page_size).limit(page_size)).all();return ItemPage(items=[self._read(x) for x in rows],page=page,page_size=page_size,total=count,total_pages=ceil(count/page_size) if count else 0)
    def detail(self,cid,iid,user):
        self.access.require_access(cid,user);item=self.db.get(PublicIntelligenceItem,iid)
        if not item or self.source(item.source_id).campaign_id!=cid:raise NotFoundError("Publicación no encontrada")
        assignments=self.access.territorial_ids(cid,user)
        if assignments is not None:
            allowed={x.parish_id for x in assignments};linked=set(self.db.scalars(select(PublicItemTerritory.parish_id).where(PublicItemTerritory.item_id==iid)))
            if not linked.intersection(allowed):raise PermissionError("Publicación fuera del alcance territorial")
        return self._read(item)
    def summary(self,cid,user):
        self.access.require_access(cid,user);sources=self.sources(cid,user);now=utcnow();items=self.items(cid,user,1,3);base=select(func.count()).select_from(PublicIntelligenceItem).join(PublicSource).where(PublicSource.campaign_id==cid)
        return SummaryRead(active_sources=sum(x.active for x in sources),official_sources=sum(x.official for x in sources),items_last_24h=self.db.scalar(base.where(PublicIntelligenceItem.fetched_at>=now-timedelta(days=1))) or 0,items_last_7_days=self.db.scalar(base.where(PublicIntelligenceItem.fetched_at>=now-timedelta(days=7))) or 0,new_documents=self.db.scalar(base.where(PublicIntelligenceItem.item_type.in_(["REPORT","DATASET","PUBLIC_DOCUMENT"]),PublicIntelligenceItem.fetched_at>=now-timedelta(days=7))) or 0,sources_with_error=sum(x.consecutive_failures>0 for x in sources),last_update=max((x.last_fetch_at for x in sources if x.last_fetch_at),default=None),latest_items=items.items)
    def link_need(self,cid,iid,user,need_id):
        self.manage(cid,user);self.detail(cid,iid,user);need=self.db.get(CitizenNeed,need_id)
        if not need or need.campaign_id!=cid:raise NotFoundError("Necesidad no encontrada")
        link=PublicItemNeedLink(item_id=iid,need_id=need_id,linked_by_user_id=user.id);self.db.add(link);self.audit.record("item_linked_to_need","SUCCESS","Publicación vinculada manualmente a necesidad",user_id=user.id,campaign_id=cid,resource_type="PUBLIC_INTELLIGENCE_ITEM",resource_id=iid);self.db.commit();return link

class PublicIntelligenceSearchService(PublicIntelligenceService):
    def search(self,campaign_id,user,query,limit=20):return self.items(campaign_id,user,1,limit,search=query).items
