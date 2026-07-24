from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from minince.shared.exceptions import MiniNCEError

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    success: bool
    data: T | None = None
    error: MiniNCEError | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: T, warnings: list[str] | None = None, **metadata: Any) -> Result[T]:
        return cls(
            success=True,
            data=data,
            warnings=warnings or [],
            metadata=metadata,
        )

    @classmethod
    def fail(cls, error: MiniNCEError, **metadata: Any) -> Result[T]:
        return cls(
            success=False,
            error=error,
            metadata=metadata,
        )

    @property
    def is_failure(self) -> bool:
        return not self.success

    def unwrap(self) -> T:
        if not self.success or self.data is None:
            raise self.error or MiniNCEError("Cannot unwrap failed result")
        return self.data

    def map(self, func: Any) -> Result[Any]:
        if self.success and self.data is not None:
            return Result.ok(func(self.data), self.warnings, **self.metadata)
        return self

    def and_then(self, func: Any) -> Result[Any]:
        if self.success and self.data is not None:
            return func(self.data)
        return self

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": self.success,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }
        if self.success:
            result["data"] = self.data
        else:
            result["error"] = self.error.to_dict() if self.error else None
        return result


@dataclass
class PageResult(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }
