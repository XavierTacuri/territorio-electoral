from sqlalchemy.orm import Session
class ElectoralProcessRepository:
    def __init__(self,db:Session):self.db=db
