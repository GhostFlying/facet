"""Access-only, single-dispatch HTTP for the locked Google Gmail client."""

from dataclasses import replace
from urllib.parse import urlsplit

import httplib2
import requests
from requests.adapters import HTTPAdapter

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure

from .retry import ProviderFailure, ProviderStage


class SyncHttp:
    """Explicit manager refresh; insert has no hidden retries or redirects."""

    def __init__(
        self, role: Role, access_token: str, *, timeout: int = 30, token_provider=None
    ):
        self._role = role
        self._token = access_token
        self._timeout = timeout
        self._token_provider = token_provider
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=0))
        self.session.mount("http://", HTTPAdapter(max_retries=0))

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        parsed = urlsplit(uri)
        supplied = headers or {}
        override = next(
            (
                value
                for key, value in supplied.items()
                if key.lower() == "x-http-method-override"
            ),
            None,
        )
        messages = parsed.path == "/gmail/v1/users/me/messages"
        allowed = method == "GET" or (
            method == "POST"
            and messages
            and (override == "GET" or (self._role is Role.TARGET and override is None))
        )
        if (
            not allowed
            or parsed.scheme != "https"
            or parsed.hostname not in {"gmail.googleapis.com", "www.googleapis.com"}
            or parsed.port not in {None, 443}
            or not parsed.path.startswith("/gmail/v1/users/me/")
        ):
            raise StorageFailure(ErrorCode.INVALID_INPUT)
        self._prepare_token(force=False)
        response = self._request(uri, method, body, supplied)
        if (
            response.status_code == 401
            and (method == "GET" or override == "GET")
            and self._token_provider is not None
        ):
            response.close()
            self._prepare_token(force=True)
            response = self._request(uri, method, body, supplied)
        try:
            return (
                httplib2.Response(
                    {**response.headers, "status": str(response.status_code)}
                ),
                response.content,
            )
        finally:
            response.close()

    def _prepare_token(self, *, force):
        if self._token_provider is None:
            return
        try:
            token = self._token_provider(force=force)
        except ProviderFailure as error:
            raise replace(error, request_dispatched=False) from None
        except StorageFailure as error:
            raise ProviderFailure(
                error.code,
                self._role,
                provider_stage=ProviderStage.TOKEN_REFRESH,
                request_dispatched=False,
            ) from None
        if type(token) is not str or not token:
            raise ProviderFailure(
                ErrorCode.INVALID_INPUT, self._role, request_dispatched=False
            )
        self._token = token

    def refresh_credentials(self):
        """Refresh only; a rejected insert is retried by the durable worker."""
        if self._token_provider is None:
            return False
        self._prepare_token(force=True)
        return True

    def _request(self, uri, method, body, supplied):
        return self.session.request(
            method,
            uri,
            data=body,
            headers={**supplied, "Authorization": "Bearer " + self._token},
            timeout=self._timeout,
            allow_redirects=False,
        )

    def close(self):
        self.session.close()
        self._token = ""
        self._token_provider = None
