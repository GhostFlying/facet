"""Bind source reconcile request scopes to the source credential revision."""

VERSION = 7

STATEMENTS = (
    "ALTER TABLE reconcile_runs ADD COLUMN source_binding_revision INTEGER "
    "NOT NULL DEFAULT 0",
)
