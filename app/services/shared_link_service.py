from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import Session
from app.models.shared_link import SharedLink


class SharedLinkService:

    def __init__(self, db: Session):
        self.db = db

    def create_link(self, file_path: str, minutes: int = 5):
        token = str(uuid.uuid4())

        link = SharedLink(
            token=token,
            file_path=file_path,
            expires_at=datetime.utcnow() + timedelta(minutes=minutes)
        )

        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)

        return link

    def get_valid_link(self, token: str):
        link = self.db.query(SharedLink).filter_by(token=token).first()

        if not link:
            return None

        if link.used:
            return None

        if datetime.utcnow() > link.expires_at:
            return None

        return link

    def mark_as_used(self, link: SharedLink):
        link.used = True
        self.db.commit()