from __future__ import annotations

import pytest

from minince.shared.exceptions import MiniNCEError, ValidationError
from minince.shared.result import PageResult, Result


class TestResult:
    def test_ok_result(self) -> None:
        result = Result.ok("data")
        assert result.success is True
        assert result.data == "data"
        assert result.error is None

    def test_ok_result_with_warnings(self) -> None:
        result = Result.ok("data", warnings=["warning1", "warning2"])
        assert result.success is True
        assert result.data == "data"
        assert result.warnings == ["warning1", "warning2"]

    def test_ok_result_with_metadata(self) -> None:
        result = Result.ok("data", extra_key="extra_value")
        assert result.metadata == {"extra_key": "extra_value"}

    def test_fail_result(self) -> None:
        error = ValidationError("Invalid data")
        result = Result.fail(error)
        assert result.success is False
        assert result.data is None
        assert result.error == error

    def test_is_failure(self) -> None:
        ok_result = Result.ok("data")
        assert ok_result.is_failure is False

        fail_result = Result.fail(ValidationError("error"))
        assert fail_result.is_failure is True

    def test_unwrap_success(self) -> None:
        result = Result.ok("value")
        assert result.unwrap() == "value"

    def test_unwrap_failure(self) -> None:
        error = ValidationError("error")
        result = Result.fail(error)
        with pytest.raises(MiniNCEError):
            result.unwrap()

    def test_map_success(self) -> None:
        result = Result.ok(5)
        mapped = result.map(lambda x: x * 2)
        assert mapped.success is True
        assert mapped.data == 10

    def test_map_failure(self) -> None:
        result = Result.fail(ValidationError("error"))
        mapped = result.map(lambda x: x * 2)
        assert mapped.success is False
        assert mapped.data is None

    def test_and_then_success(self) -> None:
        result = Result.ok(5)
        chained = result.and_then(lambda x: Result.ok(x * 3))
        assert chained.success is True
        assert chained.data == 15

    def test_and_then_failure(self) -> None:
        result = Result.fail(ValidationError("error"))
        chained = result.and_then(lambda x: Result.ok(x * 3))
        assert chained.success is False

    def test_to_dict_success(self) -> None:
        result = Result.ok("data", warnings=["warn"])
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == "data"
        assert d["warnings"] == ["warn"]
        assert "error" not in d

    def test_to_dict_failure(self) -> None:
        error = ValidationError("error msg")
        result = Result.fail(error)
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"]["code"] == "VALIDATION_ERROR"
        assert d["error"]["message"] == "error msg"


class TestPageResult:
    def test_page_result_properties(self) -> None:
        page = PageResult(
            items=[1, 2, 3],
            total=10,
            page=1,
            page_size=3,
            total_pages=4,
        )
        assert page.has_next is True
        assert page.has_prev is False

    def test_page_result_last_page(self) -> None:
        page = PageResult(
            items=[10],
            total=10,
            page=4,
            page_size=3,
            total_pages=4,
        )
        assert page.has_next is False
        assert page.has_prev is True

    def test_page_result_first_page(self) -> None:
        page = PageResult(
            items=[1, 2, 3],
            total=10,
            page=1,
            page_size=3,
            total_pages=4,
        )
        assert page.has_next is True
        assert page.has_prev is False

    def test_page_result_to_dict(self) -> None:
        page = PageResult(
            items=["a", "b"],
            total=5,
            page=2,
            page_size=2,
            total_pages=3,
        )
        d = page.to_dict()
        assert d["items"] == ["a", "b"]
        assert d["total"] == 5
        assert d["page"] == 2
        assert d["page_size"] == 2
        assert d["total_pages"] == 3
        assert d["has_next"] is True
        assert d["has_prev"] is True
