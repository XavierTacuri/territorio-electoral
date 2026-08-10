from sqlalchemy.orm import Session
class PoliticalOrganizationRepository:
    def __init__(self,db:Session):self.db=db
