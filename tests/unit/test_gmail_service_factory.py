"""Closed-error and access-only tests for the Gmail service factory."""

from datetime import UTC, datetime

import pytest

from facet.contracts import ErrorCode, Revision, Role
from facet.db.codecs import StorageFailure
from facet.gmail.credential_models import (
    AccessSnapshot,
    ClientIdText,
    ProviderSecret,
    SecretText,
    Timestamp,
)
from facet.gmail.service_factory import GoogleGmailServiceFactory


def _secret() -> ProviderSecret:
    return ProviderSecret(
        ClientIdText("client"),
        SecretText("client-secret"),
        SecretText("access"),
        SecretText("refresh"),
        Timestamp(datetime(2100, 1, 1, tzinfo=UTC)),
    )


class _Request:
    def __init__(self, result):
        self.result = result

    def execute(self, *, num_retries):
        assert num_retries == 0
        return self.result


class _Profile:
    def __init__(self, result):
        self.result = result

    def users(self):
        return self

    def getProfile(self, **_kwargs):
        return _Request(self.result)


@pytest.mark.parametrize("value", [None, {}, {"emailAddress": 1}])
def test_profile_malformed_payload_is_typed_error(monkeypatch, value):
    monkeypatch.setattr(
        GoogleGmailServiceFactory,
        "_build",
        staticmethod(lambda _role, _token: _Profile(value)),
    )
    with pytest.raises(StorageFailure) as caught:
        GoogleGmailServiceFactory().profile_account(Role.SOURCE, _secret())
    assert caught.value.code is ErrorCode.INVALID_INPUT


def test_invalid_factory_inputs_are_typed_and_mismatched_service_is_rejected():
    factory = GoogleGmailServiceFactory()
    with pytest.raises(StorageFailure) as caught:
        factory.profile_account("source", _secret())
    assert caught.value.code is ErrorCode.INVALID_INPUT
    snapshot = AccessSnapshot(
        Role.SOURCE,
        credential_revision=Revision(1),
        binding_revision=Revision(1),
        scope_policy_revision=Revision(1),
        access_token=SecretText("access"),
        expires_at=Timestamp(datetime(2100, 1, 1, tzinfo=UTC)),
    )
    with pytest.raises(StorageFailure) as caught:
        factory.service(Role.TARGET, snapshot)
    assert caught.value.code is ErrorCode.BINDING_MISMATCH


def test_google_build_uses_only_access_token_and_separate_services(monkeypatch):
    from google.oauth2 import credentials
    from googleapiclient import discovery

    observed = []
    builds = []

    def credential_spy(**kwargs):
        observed.append(kwargs)
        return object()

    def build_spy(*args, **kwargs):
        builds.append((args, kwargs))
        return object()

    monkeypatch.setattr(credentials, "Credentials", credential_spy)
    monkeypatch.setattr(discovery, "build", build_spy)
    factory = GoogleGmailServiceFactory()
    services = [
        factory.service(
            role,
            AccessSnapshot(
                role,
                Revision(1),
                Revision(1),
                Revision(1),
                SecretText("access"),
                Timestamp(datetime(2100, 1, 1, tzinfo=UTC)),
            ),
        )
        for role in (Role.SOURCE, Role.TARGET)
    ]
    assert services[0] is not services[1]
    assert observed == [{"token": "access"}, {"token": "access"}]
    assert builds[0][1]["credentials"] is not builds[1][1]["credentials"]
    assert all(args == ("gmail", "v1") for args, _ in builds)
    assert all(kwargs["cache_discovery"] is False for _, kwargs in builds)
    assert vars(factory) == {}
