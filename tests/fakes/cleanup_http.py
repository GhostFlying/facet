"""External HTTP-only Gmail fixture; contains synthetic IDs, never Facet state."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httplib2


class CleanupHttp:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        value = json.loads(self.path.read_text()) if self.path else {}
        self.ids = set(value.get("ids", ["mail1", "spam1", "draft_old"]))
        self.calls = value.get("calls", [])
        self.lost = value.get("lost", False)
        self.fail_list = value.get("fail_list", False)
        self.fail_get = value.get("fail_get", False)
        self.profile = value.get("profile", "target@example.com")

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        path = urlsplit(uri).path
        query = parse_qs(urlsplit(uri).query)
        self.calls.append((method, path, query))
        try:
            return self.respond(path, query, method)
        finally:
            if self.path:
                self.path.write_text(
                    json.dumps(
                        {
                            "ids": sorted(self.ids),
                            "calls": self.calls,
                            "lost": self.lost,
                            "fail_list": self.fail_list,
                            "fail_get": self.fail_get,
                            "profile": self.profile,
                        }
                    )
                )

    def close(self):
        pass

    def respond(self, path, query, method):
        if path.endswith("/profile"):
            value = {"emailAddress": self.profile}
        elif path.endswith("/messages"):
            assert query["includeSpamTrash"] == ["true"]
            assert query["fields"] == ["messages(id),nextPageToken"]
            if "pageToken" not in query:
                value = {"messages": [{"id": "mail1"}], "nextPageToken": "page2"}
            else:
                if self.fail_list:
                    raise TimeoutError("BODY_CREDENTIAL_SENTINEL")
                value = {"messages": [{"id": "spam1"}, {"id": "draft_old"}]}
        elif path.endswith("/drafts"):
            assert query["fields"] == ["drafts(id,message(id)),nextPageToken"]
            value = {
                "drafts": [{"id": "draft_container", "message": {"id": "draft_old"}}]
            }
        elif "/messages/" in path:
            identifier = path.rsplit("/", 1)[1]
            if method == "DELETE":
                if identifier not in self.ids:
                    return httplib2.Response({"status": "404"}), b"{}"
                self.ids.remove(identifier)
                if self.lost:
                    self.lost = False
                    raise TimeoutError("BODY_CREDENTIAL_SENTINEL")
                value = {}
            else:
                assert query["format"] == ["minimal"]
                assert query["fields"] == ["id"]
                if self.fail_get:
                    raise TimeoutError("BODY_CREDENTIAL_SENTINEL")
                if identifier not in self.ids:
                    return httplib2.Response({"status": "404"}), b"{}"
                value = {"id": identifier}
        else:
            raise AssertionError("unexpected_provider_operation")
        return httplib2.Response({"status": "200"}), json.dumps(value).encode()
