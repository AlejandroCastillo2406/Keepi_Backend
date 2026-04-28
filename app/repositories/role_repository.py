from sqlalchemy.orm import Session

from app.models.role import Role


class RoleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def count_roles(self) -> int:
        return self._db.query(Role).count()

    def add_role_rows(self, names: tuple[str, ...]) -> None:
        for name in names:
            self._db.add(Role(name=name))
