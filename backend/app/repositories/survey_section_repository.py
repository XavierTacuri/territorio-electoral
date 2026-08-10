from sqlalchemy.orm import Session
class SurveySectionRepository:
    def __init__(self, db: Session): self.db = db
