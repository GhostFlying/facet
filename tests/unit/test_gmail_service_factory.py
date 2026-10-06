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
from facet.gmail.retry import ProviderFailure
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


class _TimeoutRequest:
    def execute(self, *, num_retries):
        assert num_retries == 0
        raise TimeoutError("synthetic hanging provider")


class _Profile:
    def __init__(self, result):
        self.result = result

    def users(self):
        return self

    def getProfile(self, **_kwargs):
        return _Request(self.result)


class _TimeoutProfile:
    def users(self):
        return self

    def getProfile(self, **_kwargs):
        return _TimeoutRequest()


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


def test_profile_transport_timeout_is_typed_network_failure(monkeypatch):
    monkeypatch.setattr(
        GoogleGmailServiceFactory,
        "_build",
        staticmethod(lambda _role, _token: _TimeoutProfile()),
    )
    with pytest.raises(ProviderFailure) as caught:
        GoogleGmailServiceFactory().profile_account(Role.SOURCE, _secret())
    assert caught.value.code is ErrorCode.NETWORK_UNAVAILABLE
    assert "synthetic hanging provider" not in repr(caught.value)


def test_invalid_factory_inputs_are_typed_and_mismatched_service_is_rejected():
    factory = GoogleGmailServiceFactory()
    assert factory.supports_refresh is True
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
    import google_auth_httplib2
    from google.oauth2 import credentials
    from googleapiclient import discovery

    observed = []
    builds = []
    transports = []

    def credential_spy(**kwargs):
        observed.append(kwargs)
        return object()

    def build_spy(*args, **kwargs):
        builds.append((args, kwargs))
        return object()

    class Transport:
        def __init__(self, *, timeout):
            transports.append(timeout)

    class Authorized:
        def __init__(self, credential, *, http):
            self.credential = credential
            self.http = http

    monkeypatch.setattr(credentials, "Credentials", credential_spy)
    monkeypatch.setattr(google_auth_httplib2, "AuthorizedHttp", Authorized)
    monkeypatch.setattr("httplib2.Http", Transport)
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
    assert transports == [30, 30]
    assert all("credentials" not in kwargs for _, kwargs in builds)
    assert builds[0][1]["http"].http is not builds[1][1]["http"].http
    assert builds[0][1]["http"].credential is not builds[1][1]["http"].credential
    assert all(args == ("gmail", "v1") for args, _ in builds)
    assert all(kwargs["cache_discovery"] is False for _, kwargs in builds)
    assert all(kwargs["num_retries"] == 0 for _, kwargs in builds)
    assert vars(factory) == {}
