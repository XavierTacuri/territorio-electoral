from sqlalchemy.orm import Session
class ElectoralGeographyRepository:
    def __init__(self,db:Session):self.db=db
