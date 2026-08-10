from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.operational import ActivityType,NeedCategory
ACTIVITY_TYPES=(("TOUR","Recorrido territorial"),("COMMUNITY_MEETING","Reunión comunitaria"),("DOOR_TO_DOOR","Puerta a puerta"),("ASSEMBLY","Asamblea"),("INTERVIEW","Entrevista"),("PUBLIC_EVENT","Evento público"),("ORGANIZATION_VISIT","Visita a organización"),("BRIGADE","Brigada"),("TRAINING","Capacitación"),("PRESS_EVENT","Evento de prensa"),("OTHER","Otra actividad"))
NEED_CATEGORIES=(("DRINKING_WATER","Agua potable"),("SEWERAGE","Alcantarillado"),("ROADS","Vialidad"),("SECURITY","Seguridad"),("EMPLOYMENT","Empleo"),("TOURISM","Turismo"),("AGRICULTURE_PRODUCTION","Producción agrícola"),("HEALTH","Salud"),("EDUCATION","Educación"),("SPORTS","Deporte"),("TRANSPORT","Transporte"),("SOCIAL_CARE","Atención social"),("ENVIRONMENT","Ambiente"),("PUBLIC_SPACES","Espacios públicos"),("CONNECTIVITY","Conectividad"),("WASTE_MANAGEMENT","Gestión de residuos"),("OTHER","Otra necesidad"))
def seed(db:Session):
    for i,(code,name) in enumerate(ACTIVITY_TYPES):
        obj=db.scalar(select(ActivityType).where(ActivityType.code==code))
        if not obj:obj=ActivityType(code=code,name=name);db.add(obj)
        obj.name=name;obj.display_order=i;obj.is_active=True
    for i,(code,name) in enumerate(NEED_CATEGORIES):
        obj=db.scalar(select(NeedCategory).where(NeedCategory.code==code))
        if not obj:obj=NeedCategory(code=code,name=name);db.add(obj)
        obj.name=name;obj.display_order=i;obj.is_active=True
    db.flush()
