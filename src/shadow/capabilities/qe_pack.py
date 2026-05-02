"""Combined QE subagent pack: people & capacity + allocation + strategy (one markdown doc)."""

from __future__ import annotations

from ..models import Snapshot
from .people_capacity import render_people_capacity_md
from .resource_allocation import render_resource_allocation_md
from .strategy_lens import render_strategy_md


def render_qe_subagent_pack(snapshot: Snapshot, config: dict) -> str:
    parts = [
        render_people_capacity_md(snapshot, config),
        "\n---\n\n",
        render_resource_allocation_md(snapshot, config),
        "\n---\n\n",
        render_strategy_md(snapshot, config),
    ]
    return "".join(parts)
