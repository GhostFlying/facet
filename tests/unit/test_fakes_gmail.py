import base64
from email import policy
from email.parser import BytesParser

import pytest
from fakes.gmail import Controller, HttpFailure, InsertReply, ResponseLost
from fakes.mime import message
from googleapiclient.errors import HttpError

pytestmark = pytest.mark.usefixtures("deny_external_network")


def insert_args(raw=None):
    return {
        "userId": "me",
        "body": {
            "raw": base64.urlsafe_b64encode(
                raw if raw is not None else message()
            ).decode()
        },
        "internalDateSource": "dateHeader",
    }


def test_insert_rejects_import_only_parameter_before_request(gmail_controller):
    service = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    with pytest.raises(ValueError, match="unsupported provider"):
        service.messages().insert(**insert_args(), neverMarkSpam=True)


def test_profile_wire_has_no_scope_or_binding_oracle(gmail_controller):
    service = gmail_controller.service("source")
    facts = service.users().getProfile(userId="me").execute()
    assert facts == {
        "emailAddress": "source@example.invalid",
        "messagesTotal": 0,
        "threadsTotal": 0,
        "historyId": "701",
    }
    facts["emailAddress"] = "changed@example.invalid"
    assert (
        service.getProfile(userId="me").execute()["emailAddress"]
        == "source@example.invalid"
    )
    for field in ("scopes", "role", "binding_state", "live_verified"):
        with pytest.raises(ValueError, match="invalid profile fields"):
            gmail_controller.profile("source", {**facts, field: "invented"})
    with pytest.raises(ValueError, match="profile values"):
        gmail_controller.profile("source", {**facts, "historyId": 701})
    with pytest.raises(ValueError, match="validated profile"):
        gmail_controller.script("source", "profile.get", {"userId": "me"}, facts)


def test_message_and_thread_formats_and_copy_isolation(gmail_controller):
    raw = message(attachment=True, inline=True)
    gmail_controller.seed(
        "source",
        "message-a",
        "thread-a",
        raw,
        labels=("INBOX",),
        payload={
            "headers": [
                {"name": "From", "value": "sender@example.invalid"},
                {"name": "Subject", "value": "Synthetic"},
            ]
        },
    )
    service = gmail_controller.service("source")
    result = service.messages().get(userId="me", id="message-a", format="raw").execute()
    assert (
        base64.urlsafe_b64decode(result["raw"] + "=" * (-len(result["raw"]) % 4)) == raw
    )
    assert "payload" not in result
    result["labelIds"].append("TRASH")
    metadata = (
        service.messages()
        .get(
            userId="me", id="message-a", format="metadata", metadataHeaders=["Subject"]
        )
        .execute()
    )
    assert metadata["payload"]["headers"] == [{"name": "Subject", "value": "Synthetic"}]
    assert metadata["labelIds"] == ["INBOX"]
    thread = (
        service.threads().get(userId="me", id="thread-a", format="metadata").execute()
    )
    assert "raw" not in thread["messages"][0]
    with pytest.raises(ValueError, match="unsupported provider format"):
        service.threads().get(userId="me", id="thread-a", format="raw")
    with pytest.raises(ValueError, match="unsupported provider"):
        service.messages().get(userId="me", id="message-a", secretOracle=True)
    for forbidden in ("send", "delete", "trash", "forward", "purge"):
        assert not hasattr(service.messages(), forbidden)


@pytest.mark.parametrize(
    "resource,identifier", [("messages", "m-a"), ("threads", "t-a")]
)
@pytest.mark.parametrize(
    "selected,expected",
    [
        (None, ["From", "Subject", "sUbJeCt"]),
        ([], ["From", "Subject", "sUbJeCt"]),
        (["SUBJECT"], ["Subject", "sUbJeCt"]),
        (["fRoM"], ["From"]),
        (["Missing-Header"], []),
    ],
)
def test_metadata_is_headers_only_with_filter_and_copy_isolation(
    gmail_controller,
    resource,
    identifier,
    selected,
    expected,
):
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "synthetic.bin",
        "headers": [
            {"name": "From", "value": "sender@example.invalid"},
            {"name": "Subject", "value": "Synthetic one"},
            {"name": "sUbJeCt", "value": "Synthetic two"},
        ],
        "body": {"size": 13, "data": "Ym9keS1zZW50aW5lbA"},
        "parts": [
            {
                "mimeType": "application/octet-stream",
                "body": {"size": 7},
                "parts": [{"body": {"size": 5, "data": "bmVzdGVk"}}],
            }
        ],
    }
    gmail_controller.seed("source", "m-a", "t-a", message(), payload=payload)
    service = gmail_controller.service("source")
    endpoint = getattr(service, resource)()
    args = {"userId": "me", "id": identifier, "format": "metadata"}
    if selected is not None:
        args["metadataHeaders"] = selected

    def get_message(arguments):
        response = endpoint.get(**arguments).execute()
        return response if resource == "messages" else response["messages"][0]

    result = get_message(args)
    assert "raw" not in result and "snippet" not in result
    assert set(result["payload"]) == {"headers"}
    assert [header["name"] for header in result["payload"]["headers"]] == expected
    result["payload"]["headers"].append({"name": "Injected", "value": "local only"})
    assert [
        header["name"] for header in get_message(args)["payload"]["headers"]
    ] == expected
    # metadataHeaders only applies to metadata; full retains nested content.
    full_args = {**args, "format": "full", "metadataHeaders": ["Missing-Header"]}
    full = get_message(full_args)
    assert full["payload"] == payload and "raw" not in full
    full["payload"]["parts"][0]["parts"][0]["body"]["data"] = "changed"
    assert get_message(full_args)["payload"] == payload
    assert "payload" not in get_message({**args, "format": "minimal"})


@pytest.mark.parametrize(
    "resource,identifier", [("messages", "m-a"), ("threads", "t-a")]
)
def test_scripted_get_cannot_bypass_metadata_projection(
    gmail_controller, resource, identifier
):
    args = {
        "userId": "me",
        "id": identifier,
        "format": "metadata",
        "metadataHeaders": ["subject"],
    }
    mail = {
        "id": "m-a",
        "raw": "eA",
        "snippet": "synthetic body",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Synthetic"},
                {"name": "From", "value": "sender@example.invalid"},
            ],
            "body": {"data": "eA"},
            "parts": [{"body": {"data": "eA"}}],
        },
    }
    response = mail if resource == "messages" else {"id": "t-a", "messages": [mail]}
    gmail_controller.script("source", resource + ".get", args, response)
    result = (
        getattr(gmail_controller.service("source"), resource)().get(**args).execute()
    )
    result = result if resource == "messages" else result["messages"][0]
    assert result == {
        "id": "m-a",
        "payload": {"headers": [{"name": "Subject", "value": "Synthetic"}]},
    }


def test_nonidempotent_insert_and_indefinitely_delayed_search(
    gmail_controller, fake_clock
):
    service = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    args = insert_args()
    for _ in range(2):
        gmail_controller.script(
            "target",
            "messages.insert",
            args,
            InsertReply(rfc_id="<synthetic@example.invalid>"),
        )
    request = service.messages().insert(**args)
    assert (
        gmail_controller.identifiers("target") == ()
    )  # Construction is not execution.
    first, second = request.execute(), request.execute()
    assert first["id"] != second["id"]
    assert set(first) == {"id", "threadId", "labelIds"}
    for _ in range(3):
        fake_clock.advance(86400)
        result = (
            service.messages()
            .list(userId="me", q="rfc822msgid:<synthetic@example.invalid>")
            .execute()
        )
        assert "messages" not in result
    assert (
        service.messages()
        .get(userId="me", id=first["id"], format="raw")
        .execute()["raw"]
    )
    gmail_controller.visibility("target", first["id"], True)
    visible = (
        service.messages()
        .list(userId="me", q="rfc822msgid:<synthetic@example.invalid>")
        .execute()
    )
    assert visible["messages"] == [{"id": first["id"], "threadId": first["threadId"]}]
    assert len(service.transport.calls()) == 7
    with pytest.raises(ValueError, match="no implicit retries"):
        request.execute(num_retries=1)
    assert len(gmail_controller.identifiers("target")) == 2


@pytest.mark.parametrize("effect", [False, True])
def test_unknown_outcomes_observably_indistinguishable(gmail_controller, effect):
    args = insert_args()
    gmail_controller.script(
        "target",
        "messages.insert",
        args,
        InsertReply(effect=effect, lose_response=True),
    )
    service = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    with pytest.raises(ResponseLost, match="^synthetic response unavailable$"):
        service.messages().insert(**args).execute()
    assert service.messages().list(userId="me").execute() == {"resultSizeEstimate": 0}
    # Controller can inspect the setup truth; the application response cannot.
    assert len(gmail_controller.identifiers("target")) == int(effect)
    assert len(service.transport.calls()) == 2


def test_unmanaged_and_duplicate_rfc_ids_are_only_provider_facts(gmail_controller):
    raw = message()
    for identifier, labels in (
        ("old-copy", ()),
        ("other-copy", ("SPAM",)),
        ("third-copy", ("TRASH",)),
    ):
        gmail_controller.seed(
            "target",
            identifier,
            "separate-" + identifier,
            raw,
            labels=labels,
            rfc_id="<reused@example.invalid>",
        )
    service = gmail_controller.service("target")
    normal = (
        service.messages()
        .list(userId="me", q="rfc822msgid:<reused@example.invalid>")
        .execute()
    )
    assert len(normal["messages"]) == 1
    all_results = (
        service.messages()
        .list(
            userId="me", includeSpamTrash=True, q="rfc822msgid:<reused@example.invalid>"
        )
        .execute()
    )
    assert len(all_results["messages"]) == 3
    assert all(set(row) == {"id", "threadId"} for row in all_results["messages"])
    with pytest.raises(AssertionError, match="unsupported unscripted"):
        service.messages().list(userId="me", q="arbitrary full search").execute()


def test_source_loss_after_listing_and_missing_rfc_id(gmail_controller):
    gmail_controller.seed("source", "source-a", "thread-a", message(rfc_id=None))
    service = gmail_controller.service("source")
    assert service.messages().list(userId="me").execute()["messages"]
    gmail_controller.remove_source_fact("source-a")
    with pytest.raises(HttpError) as caught:
        service.messages().get(userId="me", id="source-a", format="raw").execute()
    assert caught.value.resp.status == 404


def test_history_pages_replay_overlap_and_final_cursor(gmail_controller):
    service = gmail_controller.service("source")
    first_args = {"userId": "me", "startHistoryId": "701"}
    first = {
        "history": [
            {
                "id": "911",
                "messages": [{"id": "m-a", "threadId": "t-a"}],
                "messagesAdded": [{"message": {"id": "m-a", "threadId": "t-a"}}],
            }
        ],
        "nextPageToken": "opaque-page",
        "historyId": "12007",
    }
    second_args = {**first_args, "pageToken": "opaque-page"}
    last = {
        "history": [
            {
                "id": "12003",
                "labelsAdded": [
                    {"message": {"id": "m-a"}, "labelIds": ["label-action"]}
                ],
            }
        ],
        "historyId": "12007",
    }
    for response_args, response in (
        (first_args, first),
        (second_args, last),
        (first_args, first),
    ):
        gmail_controller.script("source", "history.list", response_args, response)
    assert service.history().list(**first_args).execute() == first
    assert service.history().list(**second_args).execute() == last
    assert service.history().list(**first_args).execute() == first
    with pytest.raises(AssertionError, match="requires an explicit script"):
        service.history().list(**first_args).execute()
    with pytest.raises(ValueError, match="cursor must be a string"):
        service.history().list(userId="me", startHistoryId=701)


def test_later_page_failure_empty_poll_and_wrong_tokens(gmail_controller):
    service = gmail_controller.service("source")
    args = {"userId": "me", "startHistoryId": "701", "pageToken": "opaque-page"}
    gmail_controller.script("source", "history.list", args, HttpFailure(404))
    with pytest.raises(AssertionError, match="unexpected provider call"):
        service.history().list(**{**args, "pageToken": "wrong"}).execute()
    with pytest.raises(HttpError) as caught:
        service.history().list(**args).execute()
    assert caught.value.resp.status == 404
    empty_args = {"userId": "me", "startHistoryId": "12007"}
    gmail_controller.script(
        "source", "history.list", empty_args, {"historyId": "13009"}
    )
    assert service.history().list(**empty_args).execute() == {"historyId": "13009"}


def test_estimates_and_list_pagination_are_scripted_not_truth(gmail_controller):
    service = gmail_controller.service("source")
    args = {"userId": "me", "q": "after:scripted-cutoff"}
    page = {
        "messages": [{"id": "m-a", "threadId": "t-a"}],
        "resultSizeEstimate": 500,
        "nextPageToken": "opaque",
    }
    gmail_controller.script("source", "messages.list", args, page)
    gmail_controller.script(
        "source", "messages.list", {**args, "pageToken": "opaque"}, {}
    )
    assert service.messages().list(**args).execute() == page
    assert service.messages().list(**{**args, "pageToken": "opaque"}).execute() == {}


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_http_failure_uses_official_error_shape_without_classifying(
    gmail_controller, status
):
    args = insert_args()
    body = b'{"error":{"errors":[{"reason":"syntheticReason"}],"message":"synthetic"}}'
    gmail_controller.script(
        "target",
        "messages.insert",
        args,
        HttpFailure(status, body, (("retry-after", "17"),)),
    )
    service = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    with pytest.raises(HttpError) as caught:
        service.messages().insert(**args).execute()
    assert caught.value.resp.status == status
    assert caught.value.resp["retry-after"] == "17"
    assert caught.value.content == body
    assert gmail_controller.identifiers("target") == ()
    assert len(service.transport.calls()) == 1


def test_labels_legacy_facts_and_guarded_cleanup(gmail_controller):
    gmail_controller.labels(
        "source", [{"id": "action", "name": "AI/AddSender", "type": "user"}]
    )
    gmail_controller.seed("source", "m-a", "t-a", message(), labels=("action",))
    readonly = gmail_controller.service("source", scopes=frozenset({"gmail.readonly"}))
    assert (
        readonly.labels().list(userId="me").execute()["labels"][0]["name"]
        == "AI/AddSender"
    )
    args = {"userId": "me", "id": "m-a", "body": {"removeLabelIds": ["action"]}}
    with pytest.raises(HttpError) as caught:
        readonly.messages().modify(**args).execute()
    assert caught.value.resp.status == 403
    assert readonly.messages().get(userId="me", id="m-a", format="minimal").execute()[
        "labelIds"
    ] == ["action"]
    gmail_controller.script(
        "source",
        "messages.modify",
        args,
        {"id": "m-a", "threadId": "t-a", "labelIds": []},
    )
    convenience = gmail_controller.service("source", scopes=frozenset({"gmail.modify"}))
    convenience.messages().modify(**args).execute()
    assert (
        readonly.messages()
        .get(userId="me", id="m-a", format="minimal")
        .execute()["labelIds"]
        == []
    )


def test_unknown_and_unconsumed_scripts_fail(fake_clock, fake_faults):
    controller = Controller(fake_clock, fake_faults)
    controller.script(
        "source", "history.list", {"userId": "me", "startHistoryId": "701"}, {}
    )
    with pytest.raises(AssertionError, match="unconsumed provider script"):
        controller.assert_consumed()
    controller.service("source").history().list(
        userId="me", startHistoryId="701"
    ).execute()
    controller.assert_consumed()
    with pytest.raises(ValueError, match="invalid provider script"):
        controller.script("source", "invented.oracle", {}, {})


@pytest.mark.parametrize(
    "method,response",
    [
        ("messages.list", {"messages": [{"id": "m-a", "belongs_to_intent": True}]}),
        ("messages.get", {"id": "m-a", "authenticity_verified": True}),
        ("history.list", {"history": [{"id": "701", "provenance": "owned"}]}),
        (
            "labels.list",
            {"labels": [{"id": "x", "name": "x", "type": "user", "scope": "modify"}]},
        ),
    ],
)
def test_fake_refuses_scripted_nonprovider_oracles(gmail_controller, method, response):
    with pytest.raises(ValueError, match="provider wire fields"):
        gmail_controller.script("source", method, {"userId": "me"}, response)


def test_fixture_raw_budget_and_release(fake_clock, fake_faults):
    controller = Controller(fake_clock, fake_faults, raw_budget=8)
    controller.seed("source", "m-a", "t-a", b"12345678")
    with pytest.raises(ValueError, match="raw budget"):
        controller.seed("target", "m-b", "t-b", b"x")
    controller.remove_source_fact("m-a")
    controller.seed("target", "m-b", "t-b", b"12345678")


def test_legacy_and_remove_readd_events_are_observations_only(gmail_controller):
    response = {
        "history": [
            {
                "id": "711",
                "labelsAdded": [{"message": {"id": "m-a"}, "labelIds": ["action"]}],
            },
            {
                "id": "803",
                "labelsRemoved": [{"message": {"id": "m-a"}, "labelIds": ["action"]}],
            },
            {
                "id": "1007",
                "labelsAdded": [{"message": {"id": "m-a"}, "labelIds": ["action"]}],
            },
            {"id": "1201", "messagesDeleted": [{"message": {"id": "m-old"}}]},
        ],
        "historyId": "1303",
    }
    args = {"userId": "me", "startHistoryId": "701"}
    gmail_controller.script("source", "history.list", args, response)
    result = gmail_controller.service("source").history().list(**args).execute()
    assert result == response
    assert gmail_controller.identifiers("target") == ()


def test_provider_parameter_types_reject_silent_coercion(gmail_controller):
    service = gmail_controller.service("target")
    with pytest.raises(ValueError, match="argument type"):
        service.messages().list(userId="me", includeSpamTrash="false")
    with pytest.raises(ValueError, match="wire collection"):
        service.messages().insert(userId="me", body={"raw": "eA", "labelIds": "INBOX"})
    with pytest.raises(ValueError, match="invalid insert thread"):
        service.messages().insert(userId="me", body={"raw": "eA", "threadId": 1})


def test_source_loss_after_unknown_insert_retains_only_target_fact(gmail_controller):
    raw = message()
    gmail_controller.seed("source", "m-a", "t-a", raw)
    args = insert_args(raw)
    gmail_controller.script(
        "target", "messages.insert", args, InsertReply(lose_response=True)
    )
    target = gmail_controller.service("target", scopes=frozenset({"gmail.insert"}))
    with pytest.raises(ResponseLost):
        target.messages().insert(**args).execute()
    gmail_controller.remove_source_fact("m-a")
    with pytest.raises(HttpError) as caught:
        gmail_controller.service("source").messages().get(
            userId="me", id="m-a", format="raw"
        ).execute()
    assert caught.value.resp.status == 404
    assert len(gmail_controller.identifiers("target")) == 1
    assert target.messages().list(userId="me").execute() == {"resultSizeEstimate": 0}


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"html": True},
        {"attachment": True, "inline": True},
        {"rfc_id": None},
        {"date": None},
        {"date": "invalid-date"},
        {"reply_to_id": "<parent@example.invalid>"},
        {"conflicting_auth": True},
    ],
)
def test_synthetic_mime_in_memory_only(options, tmp_path):
    raw = message(**options)
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    assert isinstance(raw, bytes) and "café" in parsed["Subject"]
    assert not list(tmp_path.iterdir())
    if options.get("conflicting_auth"):
        assert len(parsed.get_all("Authentication-Results")) == 2
