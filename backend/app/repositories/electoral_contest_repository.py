from sqlalchemy.orm import Session
class ElectoralContestRepository:
    def __init__(self,db:Session):self.db=db
