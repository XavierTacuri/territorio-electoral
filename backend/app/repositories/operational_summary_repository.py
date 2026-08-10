from sqlalchemy.orm import Session

class OperationalSummaryRepository:
    def __init__(self,db:Session):self.db=db
