"""ST-02: closed code coverage and non-formatting unknown-boundary behavior."""

from dataclasses import FrozenInstanceError, replace

import pytest

from facet.contracts import ErrorClass, ErrorCode
from facet.status.errors import (
    OutputBoundaryError,
    Suggestion,
    catalog_entry,
    present_error,
)


class Trap:
    def __str__(self):
        raise AssertionError("unsafe formatting")

    def __repr__(self):
        raise AssertionError("unsafe formatting")

    def __eq__(self, other):
        raise AssertionError("unsafe comparison")


@pytest.mark.parametrize("code", tuple(ErrorCode))
def test_every_actual_code_has_fixed_presentation(code):
    entry = catalog_entry(code)
    output = present_error(code)
    assert entry.code is output.code is code
    assert type(output.error_class) is ErrorClass
    assert type(output.suggestion) is Suggestion
    assert type(output.message) is str and output.message.endswith(".")
    assert type(output.suggestion_text) is str
    assert output.failure_exit in {2, 3, 4, 5, 6, 7}
    with pytest.raises(FrozenInstanceError):
        output.message = "synthetic private sentinel"
    for field in ("message", "suggestion_text", "failure_exit", "code"):
        with pytest.raises(OutputBoundaryError, match="^consistency_failure$"):
            replace(output, **{field: Trap()})


@pytest.mark.parametrize("value", [None, "network_unavailable", 1, True, Trap()])
def test_unknown_code_never_formats_or_traverses(value):
    assert catalog_entry(value).code is ErrorCode.CONSISTENCY_FAILURE
    result = present_error(value)
    assert result.code is ErrorCode.CONSISTENCY_FAILURE
    assert result.failure_exit == 7


def test_dependency_retry_is_closed_and_never_allows_unknown_insert():
    retry = {c for c in ErrorCode if catalog_entry(c).automatic_dependency_retry}
    assert retry == {
        ErrorCode.SOURCE_RATE_LIMITED,
        ErrorCode.TARGET_RATE_LIMITED,
        ErrorCode.NETWORK_UNAVAILABLE,
    }
    assert catalog_entry(ErrorCode.INSERT_RESULT_UNKNOWN).failure_exit == 6
    assert catalog_entry(ErrorCode.DATABASE_UNAVAILABLE).failure_exit == 7
    assert catalog_entry(ErrorCode.MAINTENANCE_REQUIRED).failure_exit == 4


def test_boundary_error_retains_only_fixed_failure():
    error = OutputBoundaryError()
    assert error.code is ErrorCode.CONSISTENCY_FAILURE
    assert error.args == ("consistency_failure",)
    assert str(error) == "consistency_failure"
    assert repr(error) == "OutputBoundaryError('consistency_failure')"
    assert "sentinel" not in repr(present_error(ErrorCode.INVALID_INPUT))
