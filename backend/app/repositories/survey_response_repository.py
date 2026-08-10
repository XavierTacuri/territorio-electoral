from sqlalchemy.orm import Session
class SurveyResponseRepository:
    def __init__(self, db: Session): self.db = db
