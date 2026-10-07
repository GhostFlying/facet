"""Cleanup-only single-dispatch HTTP for the locked Google discovery client."""

from urllib.parse import urlsplit

import httplib2
import requests
from googleapiclient.discovery import build
from requests.adapters import HTTPAdapter

from facet.contracts import ErrorCode, Role
from facet.db.codecs import StorageFailure

from .retry import provider_failure


class CleanupHttp:
    """Access-only requests transport: no refresh, redirects or hidden resend."""

    def __init__(self, access_token):
        self._token = access_token
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=0))
        self.session.mount("http://", HTTPAdapter(max_retries=0))

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        parsed = urlsplit(uri)
        if (
            method not in {"GET", "DELETE"}
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
            headers={**(headers or {}), "Authorization": "Bearer " + self._token},
            timeout=30,
            allow_redirects=False,
        )
        try:
            info = httplib2.Response(
                {**response.headers, "status": str(response.status_code)}
            )
            return info, response.content
        finally:
            response.close()

    def close(self):
        self.session.close()
        self._token = ""


def build_cleanup_service(access_token):
    transport = CleanupHttp(access_token)
    try:
        return build(
            "gmail", "v1", http=transport, cache_discovery=False, num_retries=0
        )
    except Exception as error:
        transport.close()
        raise provider_failure(error, Role.TARGET) from None
