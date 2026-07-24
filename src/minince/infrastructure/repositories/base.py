from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select
from sqlalchemy.orm import Session

from minince.shared.exceptions import RepositoryError

T = TypeVar("T")


class BaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, entity: Any) -> Any:
        try:
            self.db.add(entity)
            self.db.flush()
            return entity
        except Exception as e:
            raise RepositoryError(f"Failed to add entity: {e}") from e

    def commit(self) -> None:
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise RepositoryError(f"Failed to commit: {e}") from e

    def rollback(self) -> None:
        self.db.rollback()

    def refresh(self, entity: Any) -> None:
        self.db.refresh(entity)

    def delete(self, entity: Any) -> None:
        try:
            self.db.delete(entity)
            self.db.flush()
        except Exception as e:
            raise RepositoryError(f"Failed to delete entity: {e}") from e

    def execute(self, statement: Select) -> Any:
        try:
            return self.db.execute(statement)
        except Exception as e:
            raise RepositoryError(f"Failed to execute query: {e}") from e

    def scalars(self, statement: Select) -> list[Any]:
        try:
            result = self.db.execute(statement)
            return list(result.scalars())
        except Exception as e:
            raise RepositoryError(f"Failed to execute scalar query: {e}") from e

    def scalar_one(self, statement: Select) -> Any | None:
        try:
            result = self.db.execute(statement)
            return result.scalar_one_or_none()
        except Exception as e:
            raise RepositoryError(f"Failed to execute scalar one query: {e}") from e

    def count(self, statement: Select) -> int:
        try:
            result = self.db.execute(statement)
            return len(list(result.scalars()))
        except Exception as e:
            raise RepositoryError(f"Failed to count query: {e}") from e
