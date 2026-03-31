"""Rol de usuario: solo id y nombre en BD."""

from sqlalchemy import Column, Integer, String

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name={self.name!r})>"
