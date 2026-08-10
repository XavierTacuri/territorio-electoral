from sqlalchemy.orm import Session
class SurveyResultsRepository:
    def __init__(self, db: Session): self.db = db
