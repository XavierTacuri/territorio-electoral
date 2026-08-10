from sqlalchemy.orm import Session
class ElectoralAnalyticsRepository:
    def __init__(self,db:Session):self.db=db
