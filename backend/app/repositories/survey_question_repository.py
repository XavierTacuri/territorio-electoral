from sqlalchemy.orm import Session
class SurveyQuestionRepository:
    def __init__(self, db: Session): self.db = db
