"""Current action-label observation and activation receipts; no mail content."""

# ruff: noqa: E501
VERSION = 4

STATEMENTS = (
    """CREATE TABLE current_action_receipts(
projection_id TEXT NOT NULL,
activation_id TEXT NOT NULL,
source_thread_id TEXT NOT NULL,
action_kind TEXT NOT NULL CHECK(action_kind IN('add_sender','add_domain','blacklist')),
label_id TEXT NOT NULL,
activation_sequence INTEGER NOT NULL CHECK(activation_sequence>=1),
trigger_event_id TEXT NOT NULL,
observed_at INTEGER NOT NULL,
rule_id TEXT,
rule_revision INTEGER,
thread_generation INTEGER,
admission_revision INTEGER,
outcome TEXT NOT NULL CHECK(outcome IN('applied','suppressed')),
PRIMARY KEY(projection_id,activation_id),
UNIQUE(projection_id,source_thread_id,action_kind,activation_sequence),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
FOREIGN KEY(projection_id,trigger_event_id) REFERENCES source_events(projection_id,event_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
FOREIGN KEY(projection_id,rule_id,rule_revision) REFERENCES rule_revisions(projection_id,rule_id,revision) ON DELETE RESTRICT ON UPDATE RESTRICT,
CHECK((rule_id IS NULL)=(rule_revision IS NULL)),
CHECK((thread_generation IS NULL)=(admission_revision IS NULL)),
CHECK(outcome<>'applied' OR rule_id IS NOT NULL)
) STRICT""",
    """CREATE TABLE current_action_observations(
projection_id TEXT NOT NULL,
source_thread_id TEXT NOT NULL,
action_kind TEXT NOT NULL CHECK(action_kind IN('add_sender','add_domain','blacklist')),
label_id TEXT,
present INTEGER NOT NULL CHECK(present IN(0,1)),
activation_sequence INTEGER NOT NULL CHECK(activation_sequence>=0),
activation_id TEXT,
observed_at INTEGER NOT NULL,
PRIMARY KEY(projection_id,source_thread_id,action_kind),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
FOREIGN KEY(projection_id,activation_id) REFERENCES current_action_receipts(projection_id,activation_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
CHECK(present=0 OR label_id IS NOT NULL)
) STRICT""",
    """CREATE TABLE current_action_baselines(
projection_id TEXT NOT NULL,
action_kind TEXT NOT NULL CHECK(action_kind IN('add_sender','add_domain','blacklist')),
label_id TEXT,
page_token TEXT,
complete INTEGER NOT NULL CHECK(complete IN(0,1)),
PRIMARY KEY(projection_id,action_kind),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
CHECK(complete=0 OR page_token IS NULL)
) STRICT""",
)
