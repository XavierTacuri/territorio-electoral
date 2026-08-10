from sqlalchemy.orm import Session
class ElectoralCandidateResultRepository:
    def __init__(self,db:Session):self.db=db
