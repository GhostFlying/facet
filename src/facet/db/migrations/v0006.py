"""Durable source-reconcile runs and private candidate diagnostics."""

# ruff: noqa: E501
VERSION = 6

STATEMENTS = (
    """CREATE TABLE reconcile_runs(
projection_id TEXT NOT NULL,
run_id TEXT NOT NULL,
request_key TEXT NOT NULL,
state TEXT NOT NULL CHECK(state IN('prepared','scanning','draining','completed','completed_with_issues')),
ruleset_revision INTEGER NOT NULL CHECK(ruleset_revision>=0),
window_start INTEGER NOT NULL,
window_end INTEGER NOT NULL,
discovery_cutoff INTEGER NOT NULL,
created_at INTEGER NOT NULL,
completed_at INTEGER,
page_token TEXT,
listed_count INTEGER NOT NULL CHECK(listed_count>=0),
metadata_success_count INTEGER NOT NULL CHECK(metadata_success_count>=0),
metadata_404_count INTEGER NOT NULL CHECK(metadata_404_count>=0),
matched_count INTEGER NOT NULL CHECK(matched_count>=0),
mapped_count INTEGER NOT NULL CHECK(mapped_count>=0),
queued_count INTEGER NOT NULL CHECK(queued_count>=0),
reset_count INTEGER NOT NULL CHECK(reset_count>=0),
remaining_issue_count INTEGER NOT NULL CHECK(remaining_issue_count>=0),
last_error_code TEXT,
last_provider_stage TEXT,
last_provider_reason TEXT,
last_http_status INTEGER,
revision INTEGER NOT NULL CHECK(revision>=0),
PRIMARY KEY(projection_id,run_id),
UNIQUE(projection_id,request_key),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) STRICT""",
    """CREATE TABLE reconcile_candidates(
projection_id TEXT NOT NULL,
run_id TEXT NOT NULL,
source_message_id TEXT NOT NULL,
source_thread_id TEXT NOT NULL,
classification TEXT NOT NULL CHECK(classification IN('seen','mapped','queued','no_rule','source_metadata_unavailable','duplicate_effect','attention','managed_source_missing')),
recheck_count INTEGER NOT NULL CHECK(recheck_count>=0),
first_seen_at INTEGER NOT NULL,
last_seen_at INTEGER NOT NULL,
job_id TEXT,
provider_stage TEXT,
provider_reason TEXT,
http_status INTEGER,
disposition TEXT NOT NULL CHECK(disposition IN('queued_projection','already_converged','recheck_scheduled','terminal_unknown','reset_verified','remaining_attention')),
revision INTEGER NOT NULL CHECK(revision>=0),
PRIMARY KEY(projection_id,run_id,source_message_id),
FOREIGN KEY(projection_id,run_id) REFERENCES reconcile_runs(projection_id,run_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
FOREIGN KEY(projection_id,job_id) REFERENCES sync_jobs(projection_id,job_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) STRICT""",
    "CREATE INDEX reconcile_candidates_classification ON reconcile_candidates(projection_id,run_id,classification)",
    "CREATE INDEX reconcile_runs_state ON reconcile_runs(projection_id,state,created_at)",
)
