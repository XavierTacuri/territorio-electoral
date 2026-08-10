from sqlalchemy.orm import Session
class DemographicObservationRepository:
    def __init__(self,db:Session):self.db=db
