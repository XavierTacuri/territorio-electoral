from datetime import datetime,time
from app.schemas.historical import CalendarEvent
from app.services.operational_service import OperationalService
def _dt(d,t=None):return datetime.combine(d,t or time.min)
class CalendarService:
 """Calendario de campaña: read-model que expone únicamente TerritorialActivity
 vigente (aprobada, no suspendida/cancelada). No persiste eventos propios ni
 mezcla hitos oficiales, seguimientos o encuestas — esos viven en sus propios
 módulos (Data Hub, Seguimientos legacy, Encuestas)."""
 def __init__(self,db):self.db=db;self.operations=OperationalService(db)
 def events(self,campaign_id,user,date_from,date_to):
  events=[]
  activities=self.operations.list_activities(campaign_id,user,1,500,date_from=date_from,date_to=date_to,include_inactive=False).items
  for a in activities:
   if a.approval_status!="APPROVED" or a.status in {"SUSPENDED","CANCELLED"}:continue
   events.append(CalendarEvent(id=f"activity:{a.id}",event_type="CAMPAIGN_ACTIVITY",title=a.title,starts_at=_dt(a.activity_date,a.start_time),ends_at=_dt(a.activity_date,a.end_time) if a.end_time else None,start_time=a.start_time.strftime("%H:%M") if a.start_time else None,parish_id=a.parish_id,parish_name=getattr(a,"parish_name",None),is_official=False,status=a.status,deep_link=f"/app/campaigns/{campaign_id}/activities/{a.id}"))
  events.sort(key=lambda e:e.starts_at)
  return events
