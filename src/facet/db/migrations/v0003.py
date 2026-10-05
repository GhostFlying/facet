# ruff: noqa: E501
"""Fixed v3 action-label mapping catalogue."""

VERSION = 3

_MAPPING = """CREATE TABLE action_label_mappings(
projection_id TEXT NOT NULL,
action_kind TEXT NOT NULL CHECK(action_kind IN('add_sender','add_domain','blacklist')),
label_name TEXT,
revision INTEGER NOT NULL CHECK(revision>=1),
updated_at INTEGER NOT NULL,
PRIMARY KEY(projection_id,action_kind),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
CHECK(label_name IS NULL OR (length(CAST(label_name AS BLOB)) BETWEEN 1 AND 512 AND instr(label_name,char(0))=0 AND label_name NOT GLOB '*[^ -~]*'))
) STRICT"""

_RECEIPTS = """CREATE TABLE action_label_receipts(
projection_id TEXT NOT NULL,
request_id TEXT NOT NULL,
action_kind TEXT NOT NULL CHECK(action_kind IN('add_sender','add_domain','blacklist')),
operation TEXT NOT NULL CHECK(operation IN('set','remove')),
label_name TEXT,
revision INTEGER NOT NULL CHECK(revision>=1),
observed_at INTEGER NOT NULL,
PRIMARY KEY(projection_id,request_id),
FOREIGN KEY(projection_id) REFERENCES projections(projection_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
CHECK(label_name IS NULL OR (length(CAST(label_name AS BLOB)) BETWEEN 1 AND 512 AND instr(label_name,char(0))=0 AND label_name NOT GLOB '*[^ -~]*'))
) STRICT"""

STATEMENTS = (
    _MAPPING,
    _RECEIPTS,
    "CREATE UNIQUE INDEX action_label_mapping_names ON action_label_mappings(projection_id,label_name) WHERE label_name IS NOT NULL",
)
