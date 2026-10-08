"""Retained five-minute absence decisions, not proof of failed insertion."""

# ruff: noqa: E501
VERSION = 5
_UNRESOLVED = (
    "('dispatch_started','pending_recovery','known_inserted','needs_attention')"
)
_RETIRED = "EXISTS(SELECT 1 FROM insert_absence_retries r WHERE r.projection_id=a.projection_id AND r.attempt_id=a.attempt_id)"

STATEMENTS = (
    """CREATE TABLE insert_absence_retries(
projection_id TEXT NOT NULL,
attempt_id TEXT NOT NULL,
checked_at INTEGER NOT NULL,
source_binding_revision INTEGER NOT NULL CHECK(source_binding_revision>=1),
target_binding_revision INTEGER NOT NULL CHECK(target_binding_revision>=1),
PRIMARY KEY(projection_id,attempt_id),
FOREIGN KEY(projection_id,attempt_id) REFERENCES insert_attempts(projection_id,attempt_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) STRICT""",
    """CREATE TRIGGER insert_absence_retries_valid BEFORE INSERT ON insert_absence_retries
WHEN NOT EXISTS(SELECT 1 FROM insert_attempts a WHERE a.projection_id=NEW.projection_id
AND a.attempt_id=NEW.attempt_id AND a.state='pending_recovery' AND a.certainty='unknown'
AND a.attribution='none' AND a.target_message_id IS NULL AND a.target_thread_id IS NULL
AND a.dispatch_started_at IS NOT NULL AND NEW.checked_at>=a.dispatch_started_at+300000000
AND a.rfc_message_id IS NOT NULL AND a.binding_revision=NEW.target_binding_revision)
BEGIN SELECT RAISE(ABORT,'insert_result_unknown'); END""",
    """CREATE TRIGGER insert_absence_retries_identity BEFORE UPDATE ON insert_absence_retries
BEGIN SELECT RAISE(ABORT,'request_conflict'); END""",
    """CREATE TRIGGER insert_absence_retries_retained BEFORE DELETE ON insert_absence_retries
BEGIN SELECT RAISE(ABORT,'request_conflict'); END""",
    "DROP INDEX attempts_message_unresolved",
    "DROP INDEX attempts_thread_unresolved",
    f"CREATE INDEX attempts_message_unresolved ON insert_attempts(projection_id,source_message_id) WHERE state IN {_UNRESOLVED}",
    f"CREATE INDEX attempts_thread_unresolved ON insert_attempts(projection_id,source_thread_id) WHERE state IN {_UNRESOLVED}",
    *tuple(
        f"""CREATE TRIGGER attempts_single_unresolved_{event.lower()} BEFORE {event} ON insert_attempts
WHEN NEW.state IN {_UNRESOLVED} AND NOT EXISTS(SELECT 1 FROM insert_absence_retries r
WHERE r.projection_id=NEW.projection_id AND r.attempt_id=NEW.attempt_id)
AND EXISTS(SELECT 1 FROM insert_attempts a WHERE a.projection_id=NEW.projection_id
AND a.attempt_id<>NEW.attempt_id AND a.state IN {_UNRESOLVED}
AND (a.source_message_id=NEW.source_message_id OR a.source_thread_id=NEW.source_thread_id)
AND NOT ({_RETIRED}))
BEGIN SELECT RAISE(ABORT,'insert_result_unknown'); END"""
        for event in ("INSERT", "UPDATE")
    ),
)
