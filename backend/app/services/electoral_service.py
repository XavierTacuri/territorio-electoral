from decimal import Decimal,ROUND_HALF_UP
from math import ceil
from uuid import UUID
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
from app.models.historical import *
from app.models.territory import Canton,Parish
from app.schemas.historical import *
from app.services.campaign_access_service import CampaignAccessService
from app.services.data_source_service import DataSourceService
from app.services.exceptions import BusinessRuleError,ConflictError,NotFoundError
def pct(a,b):return (Decimal(a)*100/Decimal(b)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if b else None
class ElectoralService:
 def __init__(self,db:Session):self.db=db;self.access=CampaignAccessService(db)
 def process(self,id):
  o=self.db.get(ElectoralProcess,id)
  if not o:raise NotFoundError('Proceso inexistente')
  return o
 def create_process(self,data):
  DataSourceService(self.db).get(data.source_id);o=ElectoralProcess(**data.model_dump(),is_active=True);self.db.add(o)
  try:self.db.commit();self.db.refresh(o);return o
  except IntegrityError:self.db.rollback();raise ConflictError('Proceso duplicado')
 def update_process(self,id,data):
  o=self.process(id)
  for k,v in data.model_dump(exclude_unset=True).items():setattr(o,k,v)
  self.db.commit();self.db.refresh(o);return o
 def list_processes(self,**f):
  q=select(ElectoralProcess).where(ElectoralProcess.is_active.is_(True))
  for k,col in {'year':ElectoralProcess.year,'process_type':ElectoralProcess.process_type,'status':ElectoralProcess.status,'is_final':ElectoralProcess.is_final}.items():
   if f.get(k) is not None:q=q.where(col==f[k])
  return list(self.db.scalars(q.order_by(ElectoralProcess.election_date.desc())))
 def create_contest(self,pid,data):
  self.process(pid);o=ElectoralContest(**data.model_dump(),electoral_process_id=pid,is_active=True);self.db.add(o)
  try:self.db.commit();self.db.refresh(o);return o
  except IntegrityError:self.db.rollback();raise ConflictError('Contienda duplicada')
 def contests(self,pid):self.process(pid);return list(self.db.scalars(select(ElectoralContest).where(ElectoralContest.electoral_process_id==pid,ElectoralContest.is_active.is_(True))))
 def organizations(self,source_id):
  DataSourceService(self.db).get(source_id);return list(self.db.scalars(select(PoliticalOrganization).where(PoliticalOrganization.source_id==source_id,PoliticalOrganization.is_active.is_(True)).order_by(PoliticalOrganization.name)))
 def candidates(self,pid,cid):
  self.contest(pid,cid);return list(self.db.scalars(select(ElectoralCandidate).where(ElectoralCandidate.electoral_contest_id==cid,ElectoralCandidate.is_active.is_(True)).order_by(ElectoralCandidate.ballot_order,ElectoralCandidate.full_name)))
 def geographies(self,pid,level=None,canton_id=None,is_mapped=None):
  self.process(pid);q=select(ElectoralGeography).where(ElectoralGeography.electoral_process_id==pid,ElectoralGeography.is_active.is_(True))
  if level:q=q.where(ElectoralGeography.level==level)
  if canton_id is not None:q=q.where(ElectoralGeography.canton_id==canton_id)
  if is_mapped is not None:q=q.where(ElectoralGeography.is_mapped==is_mapped)
  return list(self.db.scalars(q.order_by(ElectoralGeography.level,ElectoralGeography.external_code)))
 def contest(self,pid,cid):
  self.process(pid);o=self.db.get(ElectoralContest,cid)
  if not o or o.electoral_process_id!=pid:raise NotFoundError('Contienda inexistente')
  return o
 def turnout(self,pid,cid,level=None,**f):
  self.contest(pid,cid);q=select(ElectoralTurnout,ElectoralGeography).join(ElectoralGeography).where(ElectoralTurnout.electoral_contest_id==cid,ElectoralTurnout.is_active.is_(True))
  if level:q=q.where(ElectoralGeography.level==level)
  for k,col in {'province_id':ElectoralGeography.province_id,'canton_id':ElectoralGeography.canton_id,'parish_id':ElectoralGeography.parish_id,'geography_id':ElectoralGeography.id,'is_final':ElectoralTurnout.is_final}.items():
   if f.get(k) is not None:q=q.where(col==f[k])
  out=[]
  for t,g in self.db.execute(q):out.append(ElectoralTurnoutRead(id=t.id,electoral_contest_id=t.electoral_contest_id,electoral_geography_id=g.id,aggregation_level=g.level,registered_voters=t.registered_voters,ballots_cast=t.ballots_cast,absentee_count=t.registered_voters-t.ballots_cast,valid_votes=t.valid_votes,blank_votes=t.blank_votes,null_votes=t.null_votes,participation_rate=pct(t.ballots_cast,t.registered_voters),absentee_rate=pct(t.registered_voters-t.ballots_cast,t.registered_voters),valid_vote_rate=pct(t.valid_votes,t.ballots_cast),blank_vote_rate=pct(t.blank_votes,t.ballots_cast),null_vote_rate=pct(t.null_votes,t.ballots_cast),source_id=t.source_id,is_final=t.is_final))
  return out
 def results(self,pid,cid,level=None,**f):
  contest=self.contest(pid,cid);q=select(ElectoralCandidateResult,ElectoralCandidate,PoliticalOrganization,ElectoralGeography).join(ElectoralCandidate,ElectoralCandidate.id==ElectoralCandidateResult.electoral_candidate_id).outerjoin(PoliticalOrganization,PoliticalOrganization.id==ElectoralCandidate.political_organization_id).join(ElectoralGeography,ElectoralGeography.id==ElectoralCandidateResult.electoral_geography_id).where(ElectoralCandidateResult.electoral_contest_id==cid,ElectoralCandidateResult.is_active.is_(True))
  if level:q=q.where(ElectoralGeography.level==level)
  rows=list(self.db.execute(q));grouped={}
  for result,candidate,org,geo in rows:grouped.setdefault(geo.id,[]).append((result,candidate,org,geo))
  out=[]
  for geo_rows in grouped.values():
   valid=self.db.scalar(select(ElectoralTurnout.valid_votes).where(ElectoralTurnout.electoral_contest_id==cid,ElectoralTurnout.electoral_geography_id==geo_rows[0][3].id));ranked=sorted(geo_rows,key=lambda x:x[0].votes,reverse=True)
   for pos,(r,c,o,g) in enumerate(ranked,1):out.append(CandidateResultRead(candidate=ElectoralCandidateRead.model_validate(c),organization=PoliticalOrganizationRead.model_validate(o) if o else None,votes=r.votes,vote_share=pct(r.votes,valid) if contest.vote_method=='SINGLE_CHOICE' else None,position=pos,is_winner=pos==1 and r.is_final,source_id=r.source_id,geography_id=g.id,geography_code=g.external_code,geography_name=g.name,geography_level=g.level))
  return out
 def territorial_summary(self,pid,cid):
  contest=self.contest(pid,cid);items=[]
  for t,g in self.db.execute(select(ElectoralTurnout,ElectoralGeography).join(ElectoralGeography).where(ElectoralTurnout.electoral_contest_id==cid,ElectoralGeography.level=='PARISH')):
   ranked=list(self.db.execute(select(ElectoralCandidateResult,ElectoralCandidate).join(ElectoralCandidate).where(ElectoralCandidateResult.electoral_contest_id==cid,ElectoralCandidateResult.electoral_geography_id==g.id).order_by(ElectoralCandidateResult.votes.desc())));winner=ranked[0] if ranked else None;second=ranked[1] if len(ranked)>1 else None
   items.append({'parish_id':g.parish_id,'geography_code':g.external_code,'registered_voters':t.registered_voters,'participation_rate':pct(t.ballots_cast,t.registered_voters),'absentee_rate':pct(t.registered_voters-t.ballots_cast,t.registered_voters),'valid_votes':t.valid_votes,'blank_votes':t.blank_votes,'null_votes':t.null_votes,'winner':winner[1].display_name or winner[1].full_name if winner else None,'winner_votes':winner[0].votes if winner else None,'winner_share':pct(winner[0].votes,t.valid_votes) if winner and contest.vote_method=='SINGLE_CHOICE' else None,'margin_votes':winner[0].votes-second[0].votes if winner and second else None,'margin_points':pct(winner[0].votes-second[0].votes,t.valid_votes) if winner and second and contest.vote_method=='SINGLE_CHOICE' else None,'candidate_count':len(ranked),'is_mapped':g.is_mapped})
  return TerritorialElectoralSummary(items=items,warnings=['Existen geografías sin mapear'] if any(not x['is_mapped'] for x in items) else [])
 def comparison(self,process_ids,office_type,canton_id,level='PARISH'):
  contests=[]
  for pid in process_ids:
   found=self.db.scalar(select(ElectoralContest).where(ElectoralContest.electoral_process_id==pid,ElectoralContest.office_type==office_type,ElectoralContest.canton_id==canton_id))
   if not found:raise BusinessRuleError('Procesos incompatibles')
   contests.append(found)
  items=[]
  for c in contests:items.append({'process_id':str(c.electoral_process_id),'contest_id':str(c.id),'turnout':[x.model_dump(mode='json') for x in self.turnout(c.electoral_process_id,c.id,level)]})
  return ElectoralComparisonRead(process_ids=process_ids,office_type=office_type,canton_id=canton_id,aggregation_level=level,items=items)
 def historical_context(self,campaign_id,user,process_ids=None):
  campaign=self.access.require_access(campaign_id,user);canton=self.db.get(Canton,campaign.canton_id);q=select(ElectoralContest).join(ElectoralProcess).where(ElectoralContest.canton_id==campaign.canton_id,ElectoralContest.office_type==campaign.office_type,ElectoralProcess.is_active.is_(True))
  if process_ids:q=q.where(ElectoralProcess.id.in_(process_ids))
  contests=list(self.db.scalars(q));processes=[];turnout=[];candidate=[];unmapped=0
  for c in contests:
   p=self.process(c.electoral_process_id);processes.append({'id':str(p.id),'name':p.name,'election_date':p.election_date.isoformat(),'is_final':p.is_final});rows=self.turnout(p.id,c.id,'PARISH');turnout.append({'process_id':str(p.id),'registered_voters':sum(x.registered_voters for x in rows),'ballots_cast':sum(x.ballots_cast for x in rows)});candidate.extend([{'process_id':str(p.id),**x.model_dump(mode='json')} for x in self.results(p.id,c.id,'PARISH')]);unmapped+=self.db.scalar(select(func.count()).select_from(ElectoralGeography).where(ElectoralGeography.electoral_process_id==p.id,ElectoralGeography.is_mapped.is_(False))) or 0
  return HistoricalElectoralContextRead(campaign_id=campaign.id,canton={'id':canton.id,'name':canton.name,'dpa_code':canton.dpa_code},office_type=campaign.office_type,processes=processes,turnout_comparison=turnout,parish_comparison=[],candidate_results=candidate,data_quality={'unmapped_geographies':unmapped,'warnings':[]})
