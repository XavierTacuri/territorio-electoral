from math import ceil
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.territory import Canton, Community, Parish, Province, Sector
from app.schemas.territory import *
from app.services.exceptions import ConflictError, NotFoundError


class TerritoryService:
    def __init__(self, db:Session): self.db=db
    def provinces(self): return list(self.db.scalars(select(Province).where(Province.is_active.is_(True)).order_by(Province.name)))
    def cantons(self, province_id:int|None=None):
        q=select(Canton).where(Canton.is_active.is_(True)).order_by(Canton.name)
        if province_id:q=q.where(Canton.province_id==province_id)
        return list(self.db.scalars(q))
    def canton(self,id:int):
        value=self.db.get(Canton,id)
        if not value: raise NotFoundError("Cantón no encontrado")
        return value
    def create_canton(self,data:CantonCreate): return self._create(Canton, data.model_dump(), "Cantón duplicado")
    def update_canton(self,id:int,data:CantonUpdate): return self._update(self.canton(id),data)
    def parishes(self,canton_id:int|None=None,parish_type:str|None=None,is_active:bool|None=None):
        q=select(Parish).order_by(Parish.name)
        if canton_id:q=q.where(Parish.canton_id==canton_id)
        if parish_type:q=q.where(Parish.parish_type==parish_type)
        q=q.where(Parish.is_active.is_(True if is_active is None else is_active))
        return list(self.db.scalars(q))
    def parish(self,id:int):
        value=self.db.get(Parish,id)
        if not value: raise NotFoundError("Parroquia no encontrada")
        return value
    def create_parish(self,data:ParishCreate): self.canton(data.canton_id); return self._create(Parish,data.model_dump(mode="json"),"Parroquia duplicada")
    def update_parish(self,id:int,data:ParishUpdate): return self._update(self.parish(id),data)
    def communities(self,page:int,page_size:int,parish_id:int|None,search:str|None): return self._page(Community,page,page_size,Community.parish_id,parish_id,search)
    def community(self,id:UUID):
        value=self.db.get(Community,id)
        if not value: raise NotFoundError("Comunidad no encontrada")
        return value
    def create_community(self,data:CommunityCreate):
        self.parish(data.parish_id); values=data.model_dump(); values["location"]=self._point(data.latitude,data.longitude); return self._create(Community,values,"Comunidad duplicada")
    def update_community(self,id:UUID,data:CommunityUpdate): return self._update_place(self.community(id),data)
    def sectors(self,page:int,page_size:int,community_id:UUID|None,search:str|None): return self._page(Sector,page,page_size,Sector.community_id,community_id,search)
    def sector(self,id:UUID):
        value=self.db.get(Sector,id)
        if not value: raise NotFoundError("Sector no encontrado")
        return value
    def create_sector(self,data:SectorCreate):
        self.community(data.community_id); values=data.model_dump(); values["location"]=self._point(data.latitude,data.longitude); return self._create(Sector,values,"Sector duplicado")
    def update_sector(self,id:UUID,data:SectorUpdate): return self._update_place(self.sector(id),data)
    def _create(self,model,values,msg):
        obj=model(**values); self.db.add(obj)
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError(msg) from e
        return obj
    def _update(self,obj,data):
        for k,v in data.model_dump(exclude_unset=True).items():
            if v is None: raise ValueError(f"{k} no puede ser null")
            setattr(obj,k,v.value if hasattr(v,"value") else v)
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError("Código o nombre duplicado") from e
        return obj
    def _update_place(self,obj,data):
        values=data.model_dump(exclude_unset=True)
        for k,v in values.items(): setattr(obj,k,v)
        if "latitude" in values or "longitude" in values: obj.location=self._point(obj.latitude,obj.longitude)
        try:self.db.commit();self.db.refresh(obj)
        except IntegrityError as e:self.db.rollback();raise ConflictError("Nombre duplicado") from e
        return obj
    def _page(self,model,page,size,parent_col,parent,search):
        filters=[]
        if parent is not None:filters.append(parent_col==parent)
        if search:filters.append(func.lower(model.name).like(f"%{search.lower().strip()}%"))
        total=self.db.scalar(select(func.count()).select_from(model).where(*filters)) or 0
        items=list(self.db.scalars(select(model).where(*filters).order_by(model.name,model.id).offset((page-1)*size).limit(size)))
        return items,total,ceil(total/size) if total else 0
    @staticmethod
    def _point(lat,lon): return f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None
