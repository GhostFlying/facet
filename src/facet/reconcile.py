"""Explicit, source-only full reconcile.

The reconciler deliberately has no Target adapter.  It enumerates the sealed
source scope, records only controlled metadata, and hands eligible candidates
to a caller supplied normal projection enqueue function.  This keeps a costly
audit separate from ordinary sync while making its state restartable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from facet.contracts import (
    ErrorCode,
    LocalId,
    ProviderId,
    Revision,
    Timestamp,
)
from facet.db.codecs import StorageFailure, timestamp_to_sql
from facet.db.repositories import events
from facet.gmail.retry import ProviderFailure
from facet.gmail.source import DiscoveryItem


class ReconcileClassification(StrEnum):
    SEEN = "seen"
    MAPPED = "mapped"
    QUEUED = "queued"
    NO_RULE = "no_rule"
    METADATA_UNAVAILABLE = "source_metadata_unavailable"
    DUPLICATE_EFFECT = "duplicate_effect"
    ATTENTION = "attention"
    MANAGED_SOURCE_MISSING = "managed_source_missing"


class ReconcileDisposition(StrEnum):
    QUEUED_PROJECTION = "queued_projection"
    ALREADY_CONVERGED = "already_converged"
    RECHECK_SCHEDULED = "recheck_scheduled"
    TERMINAL_UNKNOWN = "terminal_unknown"
    RESET_VERIFIED = "reset_verified"
    REMAINING_ATTENTION = "remaining_attention"


@dataclass(frozen=True, slots=True)
class ReconcileScope:
    ruleset_revision: Revision
    window_start: Timestamp
    window_end: Timestamp
    discovery_cutoff: Timestamp


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    run_id: LocalId
    listed: int = 0
    metadata_success: int = 0
    metadata_404: int = 0
    matched: int = 0
    mapped: int = 0
    queued: int = 0
    reset: int = 0
    remaining_issue: int = 0


def _now() -> Timestamp:
    return Timestamp(datetime.now(UTC))


def _provider_details(error: ProviderFailure) -> tuple[str, str, int | None]:
    stage = error.provider_stage.value if error.provider_stage else "unknown"
    reason = error.reason.value
    return stage, reason, error.status


class SourceReconciler:
    """Run one frozen source scan against an owner and admission evaluator."""

    def __init__(
        self,
        owner,
        source,
        admission,
        scope: ReconcileScope,
        *,
        run_id=None,
        source_binding_revision=None,
    ):
        self.owner = owner
        self.source = source
        self.admission = admission
        self.scope = scope
        self.run_id = run_id or LocalId(uuid4().hex)
        self.source_binding_revision = source_binding_revision
        self._seen: set[str] = set()

    def _insert_run(self, uow, request_key: str) -> None:
        uow._execute(
            "INSERT INTO reconcile_runs(projection_id,run_id,request_key,state,"
            "ruleset_revision,source_binding_revision,window_start,window_end,discovery_cutoff,created_at,"
            "page_token,listed_count,metadata_success_count,metadata_404_count,"
            "matched_count,mapped_count,queued_count,reset_count,remaining_issue_count,"
            "revision) VALUES(?,?,?,'prepared',?,?,?,?,?,?,NULL,0,0,0,0,0,0,0,0,0)",
            (
                self.owner.projection_id.value,
                self.run_id.value,
                request_key,
                self.scope.ruleset_revision.value,
                self.source_binding_revision.value
                if self.source_binding_revision
                else 0,
                timestamp_to_sql(self.scope.window_start),
                timestamp_to_sql(self.scope.window_end),
                timestamp_to_sql(self.scope.discovery_cutoff),
                timestamp_to_sql(_now()),
            ),
        )

    def prepare(self, request_key: str) -> LocalId:
        """Persist the scope before OAuth/provider work begins."""
        with self.owner.session.transaction() as uow:
            row = uow._execute(
                "SELECT run_id,state,ruleset_revision,source_binding_revision "
                "FROM reconcile_runs "
                "WHERE projection_id=? AND request_key=?",
                (self.owner.projection_id.value, request_key),
            ).fetchone()
            if row is None:
                self._insert_run(uow, request_key)
            elif (
                int(row[2]) != self.scope.ruleset_revision.value
                or self.source_binding_revision is not None
                and int(row[3]) != self.source_binding_revision.value
            ):
                raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
            else:
                self.run_id = LocalId(row[0])
                if row[1] == "abandoned":
                    uow._execute(
                        "UPDATE reconcile_runs SET state='prepared',completed_at=NULL,"
                        "revision=revision+1 WHERE projection_id=? AND run_id=?",
                        (self.owner.projection_id.value, self.run_id.value),
                    )
        return self.run_id

    def _update_run(
        self, uow, values: dict[str, int | str | None], *, token=None
    ) -> None:
        fields = list(values)
        assignments = ",".join(f"{field}=?" for field in fields)
        params = [values[field] for field in fields]
        assignments += ",page_token=?"
        params.append(token.value if hasattr(token, "value") else token)
        params.extend(
            (
                self.owner.projection_id.value,
                self.run_id.value,
                self.scope.ruleset_revision.value,
            )
        )
        uow._execute(
            f"UPDATE reconcile_runs SET {assignments},revision=revision+1 "
            "WHERE projection_id=? AND run_id=? AND ruleset_revision=?",
            params,
        )

    def run(self, request_key: str, *, enqueue_candidate=None) -> ReconcileResult:
        """Scan all pages; provider reads happen outside SQLite transactions."""
        page = None
        totals = {
            name: 0
            for name in (
                "listed",
                "metadata_success",
                "metadata_404",
                "matched",
                "mapped",
                "queued",
                "reset",
                "remaining_issue",
            )
        }
        self.totals = totals
        with self.owner.session.transaction() as uow:
            existing = uow._execute(
                "SELECT run_id,state,page_token,listed_count,metadata_success_count,"
                "metadata_404_count,matched_count,mapped_count,queued_count,"
                "reset_count,remaining_issue_count,ruleset_revision "
                "FROM reconcile_runs "
                "WHERE projection_id=? AND request_key=?",
                (self.owner.projection_id.value, request_key),
            ).fetchone()
            if existing is None:
                self._insert_run(uow, request_key)
                uow._execute(
                    "UPDATE reconcile_runs SET state='running',revision=revision+1 "
                    "WHERE projection_id=? AND run_id=?",
                    (self.owner.projection_id.value, self.run_id.value),
                )
            else:
                if existing[1] == "abandoned":
                    self.run_id = LocalId(existing[0])
                    uow._execute(
                        "UPDATE reconcile_runs SET state='running',completed_at=NULL,"
                        "page_token=NULL,listed_count=0,metadata_success_count=0,"
                        "metadata_404_count=0,matched_count=0,mapped_count=0,"
                        "queued_count=0,reset_count=0,remaining_issue_count=0,"
                        "last_error_code=NULL,last_provider_stage=NULL,"
                        "last_provider_reason=NULL,last_http_status=NULL,"
                        "revision=revision+1 WHERE projection_id=? AND run_id=?",
                        (self.owner.projection_id.value, self.run_id.value),
                    )
                    existing = None
                elif existing[1] == "prepared":
                    self.run_id = LocalId(existing[0])
                    uow._execute(
                        "UPDATE reconcile_runs SET state='running',revision=revision+1 "
                        "WHERE projection_id=? AND run_id=?",
                        (self.owner.projection_id.value, self.run_id.value),
                    )
                    existing = None
                if existing is None:
                    pass
                elif int(existing[11]) != self.scope.ruleset_revision.value:
                    raise StorageFailure(ErrorCode.REQUEST_CONFLICT)
                elif existing[1] in {"completed", "completed_with_issues"}:
                    return ReconcileResult(
                        LocalId(existing[0]),
                        *[int(existing[index] or 0) for index in range(3, 11)],
                    )
                if existing is not None:
                    uow._execute(
                        "UPDATE reconcile_runs SET state='abandoned',completed_at=?,"
                        "revision=revision+1 WHERE projection_id=? AND run_id=?",
                        (
                            timestamp_to_sql(_now()),
                            self.owner.projection_id.value,
                            existing[0],
                        ),
                    )
                    request_key = f"{request_key}:retry:{uuid4().hex}"
                    self.run_id = LocalId(uuid4().hex)
                    self._insert_run(uow, request_key)
                    uow._execute(
                        "UPDATE reconcile_runs SET state='running',revision=revision+1 "
                        "WHERE projection_id=? AND run_id=?",
                        (self.owner.projection_id.value, self.run_id.value),
                    )
        query = self.admission.discovery_query(None)
        if query is None:
            with self.owner.session.transaction() as uow:
                uow._execute(
                    "UPDATE reconcile_runs SET state='draining',revision=revision+1 "
                    "WHERE projection_id=? AND run_id=?",
                    (self.owner.projection_id.value, self.run_id.value),
                )
            self._scan_tracked_threads(totals, enqueue_candidate)
            self._scan_legacy_source_missing(totals, enqueue_candidate)
            self._finish(totals, with_issues=totals["remaining_issue"] > 0)
            return ReconcileResult(self.run_id, **totals)
        while True:
            self._assert_scope_revision()
            response = self.source.discover(
                window_start=self.scope.window_start.value,
                window_end=self.scope.window_end.value,
                page_token=page,
                query=query,
            )
            batch_results = {}
            batch_reader = getattr(self.source, "reconcile_candidates_batch", None)
            if callable(batch_reader):
                pending_items = tuple(
                    item
                    for item in response.items
                    if item.message_id.value not in self._seen
                )
                for offset in range(0, len(pending_items), 50):
                    batch_results.update(
                        batch_reader(pending_items[offset : offset + 50])
                    )
            for item in response.items:
                if item.message_id.value in self._seen:
                    continue
                self._seen.add(item.message_id.value)
                totals["listed"] += 1
                try:
                    candidate = batch_results.get(item.message_id.value)
                    if candidate is None:
                        read_candidate = getattr(
                            self.source, "reconcile_candidate", self.source.candidate
                        )
                        candidate = read_candidate(item)
                    if isinstance(candidate, ProviderFailure):
                        raise candidate
                except ProviderFailure as error:
                    stage, reason, status = _provider_details(error)
                    if status == 404:
                        totals["metadata_404"] += 1
                        totals["remaining_issue"] += 1
                        self._record(
                            item,
                            ReconcileClassification.METADATA_UNAVAILABLE,
                            ReconcileDisposition.RECHECK_SCHEDULED,
                            stage,
                            reason,
                            status,
                        )
                    else:
                        totals["remaining_issue"] += 1
                        self._record(
                            item,
                            ReconcileClassification.ATTENTION,
                            ReconcileDisposition.REMAINING_ATTENTION,
                            stage,
                            reason,
                            status,
                        )
                    continue
                if candidate.attention is not None:
                    totals["remaining_issue"] += 1
                    self._record(
                        item,
                        ReconcileClassification.ATTENTION,
                        ReconcileDisposition.REMAINING_ATTENTION,
                        "message_get",
                        candidate.attention.reason.value,
                        None,
                    )
                    continue
                totals["metadata_success"] += 1
                value = candidate.candidate
                if value.is_draft:
                    self._record(
                        item,
                        ReconcileClassification.NO_RULE,
                        ReconcileDisposition.ALREADY_CONVERGED,
                        None,
                        "draft",
                        None,
                    )
                    continue
                if not (
                    self.scope.window_start.value
                    <= value.observed_at.value
                    <= self.scope.window_end.value
                ):
                    self._record(
                        item,
                        ReconcileClassification.NO_RULE,
                        ReconcileDisposition.ALREADY_CONVERGED,
                        None,
                        "outside_window",
                        None,
                    )
                    continue
                decision = self.admission._policy.evaluate(
                    value, _now(), prospective=True
                )
                if not decision.admit:
                    self._record(
                        item,
                        ReconcileClassification.NO_RULE,
                        ReconcileDisposition.RESET_VERIFIED,
                        None,
                        "no_rule",
                        None,
                    )
                    totals["reset"] += 1
                    continue
                totals["matched"] += 1
                with self.owner.session.transaction() as uow:
                    mapped = uow._execute(
                        "SELECT 1 FROM message_mappings "
                        "WHERE projection_id=? AND source_message_id=? LIMIT 1",
                        (self.owner.projection_id.value, item.message_id.value),
                    ).fetchone()
                if mapped is not None:
                    totals["mapped"] += 1
                    self._record(
                        item,
                        ReconcileClassification.MAPPED,
                        ReconcileDisposition.ALREADY_CONVERGED,
                        None,
                        "mapping",
                        None,
                    )
                    continue
                if enqueue_candidate is None:
                    totals["remaining_issue"] += 1
                    self._record(
                        item,
                        ReconcileClassification.ATTENTION,
                        ReconcileDisposition.REMAINING_ATTENTION,
                        None,
                        "enqueue_unavailable",
                        None,
                    )
                elif enqueue_candidate(value, decision.rule):
                    totals["queued"] += 1
                    self._record(
                        item,
                        ReconcileClassification.QUEUED,
                        ReconcileDisposition.QUEUED_PROJECTION,
                        None,
                        "queued",
                        None,
                    )
                else:
                    totals["remaining_issue"] += 1
                    self._record(
                        item,
                        ReconcileClassification.ATTENTION,
                        ReconcileDisposition.REMAINING_ATTENTION,
                        None,
                        "enqueue_rejected",
                        None,
                    )
            page = response.next_page_token
            with self.owner.session.transaction() as uow:
                self._update_run(
                    uow,
                    {f"{name}_count": value for name, value in totals.items()},
                    token=page,
                )
            if page is None:
                break
        with self.owner.session.transaction() as uow:
            uow._execute(
                "UPDATE reconcile_runs SET state='draining',revision=revision+1 "
                "WHERE projection_id=? AND run_id=?",
                (self.owner.projection_id.value, self.run_id.value),
            )
        self._scan_tracked_threads(totals, enqueue_candidate)
        self._scan_legacy_source_missing(totals, enqueue_candidate)
        self._finish(totals, with_issues=totals["remaining_issue"] > 0)
        return ReconcileResult(self.run_id, **totals)

    def _assert_scope_revision(self):
        with self.owner.session.transaction() as uow:
            row = uow._execute(
                "SELECT p.ruleset_revision,b.binding_revision,b.state "
                "FROM projections p JOIN bindings b ON b.projection_id=p.projection_id "
                "AND b.role='source' WHERE p.projection_id=?",
                (self.owner.projection_id.value,),
            ).fetchone()
        if (
            row is None
            or int(row[0]) != self.scope.ruleset_revision.value
            or self.source_binding_revision is not None
            and int(row[1]) != self.source_binding_revision.value
            or row[2] != "verified"
        ):
            raise StorageFailure(ErrorCode.REQUEST_CONFLICT)

    def _scan_legacy_source_missing(self, totals, enqueue_candidate):
        with self.owner.session.transaction() as uow:
            rows = uow._execute(
                "SELECT source_message_id,source_thread_id FROM source_events "
                "WHERE projection_id=? AND tag='message_added' "
                "AND processing='source_missing' AND source_message_id IS NOT NULL",
                (self.owner.projection_id.value,),
            ).fetchall()
        for message_id, thread_id in rows:
            if message_id in self._seen:
                continue
            self._seen.add(message_id)
            item = DiscoveryItem(ProviderId(message_id), ProviderId(thread_id))
            try:
                read_candidate = getattr(
                    self.source, "reconcile_candidate", self.source.candidate
                )
                result = read_candidate(item)
            except ProviderFailure as error:
                stage, reason, status = _provider_details(error)
                if status == 404:
                    totals["metadata_404"] += 1
                    totals["remaining_issue"] += 1
                    self._record(
                        item,
                        ReconcileClassification.METADATA_UNAVAILABLE,
                        ReconcileDisposition.RECHECK_SCHEDULED,
                        stage,
                        reason,
                        status,
                    )
                else:
                    totals["remaining_issue"] += 1
                    self._record(
                        item,
                        ReconcileClassification.ATTENTION,
                        ReconcileDisposition.REMAINING_ATTENTION,
                        stage,
                        reason,
                        status,
                    )
                continue
            if result.attention is not None:
                totals["remaining_issue"] += 1
                self._record(
                    item,
                    ReconcileClassification.ATTENTION,
                    ReconcileDisposition.REMAINING_ATTENTION,
                    "message_get",
                    result.attention.reason.value,
                    None,
                )
            else:
                totals["metadata_success"] += 1
                value = result.candidate
                if value.is_draft:
                    self._record(
                        item,
                        ReconcileClassification.NO_RULE,
                        ReconcileDisposition.RESET_VERIFIED,
                        None,
                        "draft",
                        None,
                    )
                    totals["reset"] += 1
                    continue
                decision = self.admission._policy.evaluate(
                    value, _now(), prospective=True
                )
                with self.owner.session.transaction() as uow:
                    mapped = uow._execute(
                        "SELECT 1 FROM message_mappings "
                        "WHERE projection_id=? AND source_message_id=? LIMIT 1",
                        (self.owner.projection_id.value, message_id),
                    ).fetchone()
                if mapped is not None:
                    totals["mapped"] += 1
                    totals["reset"] += 1
                    with self.owner.session.transaction() as uow:
                        events.converge_source_missing(
                            uow,
                            self.owner.projection_id,
                            ProviderId(message_id),
                            _now(),
                        )
                    self._record(
                        item,
                        ReconcileClassification.MAPPED,
                        ReconcileDisposition.RESET_VERIFIED,
                        None,
                        "mapping",
                        None,
                    )
                elif decision.admit and enqueue_candidate is not None:
                    if enqueue_candidate(value, decision.rule):
                        totals["matched"] += 1
                        totals["queued"] += 1
                        with self.owner.session.transaction() as uow:
                            events.converge_source_missing(
                                uow,
                                self.owner.projection_id,
                                ProviderId(message_id),
                                _now(),
                            )
                        self._record(
                            item,
                            ReconcileClassification.QUEUED,
                            ReconcileDisposition.QUEUED_PROJECTION,
                            None,
                            "legacy_source_missing_recovered",
                            None,
                        )
                    else:
                        totals["remaining_issue"] += 1
                        self._record(
                            item,
                            ReconcileClassification.ATTENTION,
                            ReconcileDisposition.REMAINING_ATTENTION,
                            None,
                            "enqueue_rejected",
                            None,
                        )
                else:
                    totals["reset"] += 1
                    with self.owner.session.transaction() as uow:
                        events.converge_source_missing(
                            uow,
                            self.owner.projection_id,
                            ProviderId(message_id),
                            _now(),
                        )
                    self._record(
                        item,
                        ReconcileClassification.NO_RULE,
                        ReconcileDisposition.RESET_VERIFIED,
                        "message_get",
                        "legacy_source_missing_converged",
                        None,
                    )

    def _scan_tracked_threads(self, totals, enqueue_candidate):
        """Read complete available history for each active tracked thread."""
        with self.owner.session.transaction() as uow:
            rows = uow._execute(
                "SELECT source_thread_id FROM tracked_threads "
                "WHERE projection_id=? AND active=1",
                (self.owner.projection_id.value,),
            ).fetchall()
        for (thread_id,) in rows:
            try:
                history = self.source.thread_metadata(
                    ProviderId(thread_id), include_spam_trash=True
                )
            except ProviderFailure as error:
                stage, reason, status = _provider_details(error)
                totals["remaining_issue"] += 1
                totals["metadata_404"] += status == 404
                item = DiscoveryItem(ProviderId(thread_id), ProviderId(thread_id))
                self._record(
                    item,
                    ReconcileClassification.MANAGED_SOURCE_MISSING
                    if status == 404
                    else ReconcileClassification.ATTENTION,
                    ReconcileDisposition.REMAINING_ATTENTION,
                    stage,
                    reason,
                    status,
                )
                continue
            for message in history.messages:
                if "DRAFT" in message.labels:
                    continue
                if message.message_id.value in self._seen:
                    continue
                self._seen.add(message.message_id.value)
                totals["metadata_success"] += 1
                item = DiscoveryItem(message.message_id, message.thread_id)
                with self.owner.session.transaction() as uow:
                    mapped = uow._execute(
                        "SELECT 1 FROM message_mappings "
                        "WHERE projection_id=? AND source_message_id=? LIMIT 1",
                        (self.owner.projection_id.value, message.message_id.value),
                    ).fetchone()
                if mapped is not None:
                    totals["mapped"] += 1
                    self._record(
                        item,
                        ReconcileClassification.MAPPED,
                        ReconcileDisposition.ALREADY_CONVERGED,
                        None,
                        "mapping",
                        None,
                    )
                elif enqueue_candidate is not None and enqueue_candidate(message, None):
                    totals["matched"] += 1
                    totals["queued"] += 1
                    self._record(
                        item,
                        ReconcileClassification.QUEUED,
                        ReconcileDisposition.QUEUED_PROJECTION,
                        None,
                        "tracked_history",
                        None,
                    )
                else:
                    totals["remaining_issue"] += 1
                    self._record(
                        item,
                        ReconcileClassification.ATTENTION,
                        ReconcileDisposition.REMAINING_ATTENTION,
                        None,
                        "enqueue_unavailable",
                        None,
                    )

    def _record(self, item, classification, disposition, stage, reason, status):
        self._assert_scope_revision()
        now = timestamp_to_sql(_now())
        with self.owner.session.transaction() as uow:
            previous = uow._execute(
                "SELECT recheck_count FROM reconcile_candidates "
                "WHERE projection_id=? AND source_message_id=? "
                "ORDER BY last_seen_at DESC LIMIT 1",
                (self.owner.projection_id.value, item.message_id.value),
            ).fetchone()
            rechecks = int(previous[0]) if previous is not None else 0
            if classification is ReconcileClassification.METADATA_UNAVAILABLE:
                rechecks += 1
                if rechecks > 1:
                    disposition = ReconcileDisposition.TERMINAL_UNKNOWN
            uow._execute(
                "INSERT OR REPLACE INTO reconcile_candidates(projection_id,run_id,"
                "source_message_id,source_thread_id,classification,recheck_count,"
                "first_seen_at,last_seen_at,job_id,provider_stage,provider_reason,"
                "http_status,disposition,revision) "
                "VALUES(?,?,?,?,?,?,?,? ,NULL,?,?,?, ?,0)",
                (
                    self.owner.projection_id.value,
                    self.run_id.value,
                    item.message_id.value,
                    item.thread_id.value,
                    classification.value,
                    rechecks,
                    now,
                    now,
                    stage,
                    reason,
                    status,
                    disposition.value,
                ),
            )

    def _finish(self, totals, *, with_issues):
        with self.owner.session.transaction() as uow:
            self._update_run(
                uow, {f"{name}_count": value for name, value in totals.items()}
            )
            uow._execute(
                "UPDATE reconcile_runs SET state=?,completed_at=?,"
                "remaining_issue_count=?,"
                "revision=revision+1 WHERE projection_id=? AND run_id=?",
                (
                    "completed_with_issues" if with_issues else "completed",
                    timestamp_to_sql(_now()),
                    totals["remaining_issue"],
                    self.owner.projection_id.value,
                    self.run_id.value,
                ),
            )
