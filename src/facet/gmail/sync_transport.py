"""Access-only, single-dispatch HTTP for the locked Google Gmail client."""

from urllib.parse import urlsplit

import httplib2
import requests
from requests.adapters import HTTPAdapter

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure


class SyncHttp:
    """No hidden retries, redirects or credential refresh after dispatch."""

    def __init__(self, role: Role, access_token: str, *, timeout: int = 30):
        self._role = role
        self._token = access_token
        self._timeout = timeout
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
        response = self.session.request(
            method,
            uri,
            data=body,
            headers={**supplied, "Authorization": "Bearer " + self._token},
            timeout=self._timeout,
            allow_redirects=False,
        )
        try:
            return (
                httplib2.Response(
                    {**response.headers, "status": str(response.status_code)}
                ),
                response.content,
            )
        finally:
            response.close()

    def close(self):
        self.session.close()
        self._token = ""
