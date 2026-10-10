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
from facet.gmail.retry import ProviderFailure, ProviderStage
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
        self.closed = False

    def close(self):
        self.closed = True

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
    assert caught.value.provider_stage is ProviderStage.PROFILE_PROBE
    assert caught.value.timeout_seconds == 30
    assert caught.value.attempt == 1
    assert caught.value.observed_at is not None
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

    builds = []

    def forbidden(*args, **kwargs):
        raise AssertionError("sync must not construct auto-refresh/replay clients")

    class BuiltService:
        pass

    def build_spy(*args, **kwargs):
        builds.append((args, kwargs))
        return BuiltService()

    monkeypatch.setattr(credentials, "Credentials", forbidden)
    monkeypatch.setattr(google_auth_httplib2, "AuthorizedHttp", forbidden)
    monkeypatch.setattr("httplib2.Http", forbidden)
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
    assert all("credentials" not in kwargs for _, kwargs in builds)
    assert builds[0][1]["http"] is not builds[1][1]["http"]
    assert builds[0][1]["http"].session is not builds[1][1]["http"].session
    for (_, kwargs), role in zip(builds, Role, strict=True):
        http = kwargs["http"]
        assert http._role is role
        assert http._token == "access"
        assert http._timeout == 30
        assert http.session.get_adapter("https://").max_retries.total == 0
        http.close()
        assert http._token == ""
    assert all(args == ("gmail", "v1") for args, _ in builds)
    assert all(kwargs["cache_discovery"] is False for _, kwargs in builds)
    assert all(kwargs["num_retries"] == 0 for _, kwargs in builds)
    assert all(
        service.facet_domain_query_capability == "gmail-from-domain-v1"
        for service in services
    )
    assert vars(factory) == {}


def test_google_discovery_timeout_is_typed_and_stage_bounded(monkeypatch):
    import googleapiclient.discovery

    monkeypatch.setattr(
        googleapiclient.discovery,
        "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TimeoutError("synthetic discovery timeout")
        ),
    )
    snapshot = AccessSnapshot(
        Role.SOURCE,
        Revision(1),
        Revision(1),
        Revision(1),
        SecretText("access"),
        Timestamp(datetime(2100, 1, 1, tzinfo=UTC)),
    )
    with pytest.raises(ProviderFailure) as caught:
        GoogleGmailServiceFactory().service(Role.SOURCE, snapshot)
    assert caught.value.code is ErrorCode.NETWORK_UNAVAILABLE
    assert caught.value.provider_stage is ProviderStage.SERVICE_DISCOVERY
    assert caught.value.timeout_seconds == 30
    assert "synthetic discovery timeout" not in repr(caught.value)


@pytest.mark.parametrize("value", [{"emailAddress": "source@example.com"}, {}])
def test_profile_closes_service_on_success_and_malformed_payload(monkeypatch, value):
    service = _Profile(value)
    monkeypatch.setattr(
        GoogleGmailServiceFactory, "_build", staticmethod(lambda *_args: service)
    )
    if value:
        GoogleGmailServiceFactory().profile_account(Role.SOURCE, _secret())
    else:
        with pytest.raises(StorageFailure):
            GoogleGmailServiceFactory().profile_account(Role.SOURCE, _secret())
    assert service.closed


def test_failed_discovery_closes_transport(monkeypatch):
    from facet.gmail.sync_transport import SyncHttp

    closed = []
    original = SyncHttp.close

    def close(self):
        original(self)
        closed.append(self)

    monkeypatch.setattr(SyncHttp, "close", close)
    monkeypatch.setattr(
        "googleapiclient.discovery.build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(ProviderFailure):
        GoogleGmailServiceFactory._build(Role.SOURCE, "access")
    assert len(closed) == 1
    assert closed[0]._token == ""
