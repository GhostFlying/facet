"""Read-only HTTP dashboard boundary."""

from .server import DashboardServer, SnapshotProvider, serve_dashboard

__all__ = ("DashboardServer", "SnapshotProvider", "serve_dashboard")
