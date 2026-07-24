from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from minince.shared.exceptions import MiniNCEError


@dataclass
class Result:
    success: bool
    data: Any = None
    error: MiniNCEError | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any = None, warnings: list[str] | None = None, **metadata: Any) -> Result:
        return cls(
            success=True,
            data=data,
            warnings=warnings or [],
            metadata=metadata,
        )

    @classmethod
    def fail(cls, error: MiniNCEError, **metadata: Any) -> Result:
        return cls(
            success=False,
            error=error,
            metadata=metadata,
        )

    @property
    def is_failure(self) -> bool:
        return not self.success

    def unwrap(self) -> Any:
        if not self.success or self.data is None:
            raise self.error or MiniNCEError("Cannot unwrap failed result")
        return self.data

    def map(self, func: Any) -> Result:
        if self.success and self.data is not None:
            return Result.ok(func(self.data), self.warnings, **self.metadata)
        return self

    def and_then(self, func: Any) -> Result:
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
class PageResult:
    items: list[Any]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1

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
