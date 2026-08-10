from sqlalchemy.orm import Session
class ElectoralCandidateRepository:
    def __init__(self,db:Session):self.db=db
