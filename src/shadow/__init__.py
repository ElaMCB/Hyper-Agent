"""Shadow core: snapshot spine, adapters, capabilities."""

from .models import Action, Defect, Snapshot, TestRun
from .snapshot import build_snapshot

__all__ = ["Action", "Defect", "Snapshot", "TestRun", "build_snapshot"]
