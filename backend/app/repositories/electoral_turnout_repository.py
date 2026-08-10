from sqlalchemy.orm import Session
class ElectoralTurnoutRepository:
    def __init__(self,db:Session):self.db=db
