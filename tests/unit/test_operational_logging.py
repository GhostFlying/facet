"""Closed local diagnostic hashes/reasons never become public records."""

import json

import pytest

from facet.contracts import ErrorCode, Role, Sha256Hex
from facet.gmail.retry import ProviderFailure, ProviderReason, ProviderStage, execute
from facet.status.errors import OutputBoundaryError
from facet.status.logging import OperationStage, emit_operation
from facet.status.serialization import serialize_public


def test_full_eml_digest_is_local_typed_diagnostic_only(capfd):
    digest = Sha256Hex("ab" * 32)
    emit_operation(
        OperationStage.PROJECTION, code=ErrorCode.FIDELITY_MISMATCH, raw_digest=digest
    )
    event = json.loads(capfd.readouterr().err)
    assert event["raw_digest"] == digest.value
    assert event["code"] == "fidelity_mismatch"
    with pytest.raises(OutputBoundaryError):
        serialize_public(event)
    with pytest.raises(OutputBoundaryError):
        emit_operation(OperationStage.PROJECTION, raw_digest="PRIVATE_BODY_SENTINEL")
    output = capfd.readouterr().err
    assert "PRIVATE_BODY_SENTINEL" not in output
    assert output == ""


def test_handled_provider_error_preserves_closed_reason_stage_and_retry(capfd):
    class Request:
        def execute(self, **kwargs):
            raise ProviderFailure(
                ErrorCode.TARGET_RATE_LIMITED,
                Role.TARGET,
                403,
                60,
                ProviderStage.MESSAGE_GET,
                reason=ProviderReason.USER_RATE_LIMIT,
            )

    with pytest.raises(ProviderFailure):
        execute(Request(), Role.TARGET, provider_stage=ProviderStage.MESSAGE_GET)
    event = json.loads(capfd.readouterr().err)
    assert event["reason"] == "userRateLimitExceeded"
    assert event["provider_stage"] == "message_get"
    assert event["retry_after_seconds"] == 60 and event["http_status"] == 403
    assert "raw" not in event and "message" not in event
