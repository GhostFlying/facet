"""Public output primitives. Importing this package performs no logging setup."""

from .errors import Suggestion, catalog_entry, present_error
from .logging import configure_production_logging, emit_safe
from .models import (
    CheckState,
    Component,
    Diagnostics,
    EpochSummary,
    IssueGroup,
    Issues,
    LatencyMetric,
    PermissionMode,
    Pressure,
    Progress,
    PublicEnvelope,
    QueueCounts,
    RateMetric,
    RoleStatus,
    Status,
)
from .serialization import public_json, serialize_public

__all__ = (
    "PublicEnvelope",
    "Status",
    "Progress",
    "Issues",
    "Diagnostics",
    "RoleStatus",
    "EpochSummary",
    "QueueCounts",
    "RateMetric",
    "LatencyMetric",
    "IssueGroup",
    "PermissionMode",
    "CheckState",
    "Pressure",
    "Component",
    "Suggestion",
    "serialize_public",
    "public_json",
    "catalog_entry",
    "present_error",
    "emit_safe",
    "configure_production_logging",
)
