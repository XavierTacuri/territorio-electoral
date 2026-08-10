from sqlalchemy.orm import Session
class DataImportRepository:
    def __init__(self,db:Session):self.db=db
