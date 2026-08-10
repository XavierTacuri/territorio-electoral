from sqlalchemy.orm import Session
class DemographicIndicatorRepository:
    def __init__(self,db:Session):self.db=db
