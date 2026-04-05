"""Fetch open Bugs from Azure DevOps (WIQL + Work Items REST API)."""

import base64
import os
from typing import Any

import requests

from ..models import Defect

DEFAULT_WIQL = """
SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Severity], [System.CreatedDate]
FROM WorkItems
WHERE [System.WorkItemType] = 'Bug'
AND [System.State] <> 'Closed'
ORDER BY [Microsoft.VSTS.Common.Severity] ASC, [System.CreatedDate] DESC
""".strip()


class AzureDevOpsAdapter:
    """Read bugs from a project using a Personal Access Token (PAT)."""

    def __init__(
        self,
        organization: str,
        project: str,
        pat: str,
        *,
        wiql: str | None = None,
        max_items: int = 75,
    ):
        self.organization = organization.strip().rstrip("/")
        self.project = project.strip()
        self.pat = pat
        self.wiql = (wiql or DEFAULT_WIQL).strip()
        self.max_items = max_items
        self._base = f"https://dev.azure.com/{self.organization}/{self.project}"

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "AzureDevOpsAdapter":
        org = (cfg.get("organization") or os.getenv("AZDO_ORG") or "").strip()
        project = (cfg.get("project") or os.getenv("AZDO_PROJECT") or "").strip()
        pat = os.getenv(cfg.get("pat_env", "AZDO_PAT"), "") or os.getenv("AZDO_PAT", "")
        if not pat:
            raise ValueError("Azure DevOps PAT missing. Set AZDO_PAT in .env (see .env.example).")
        if not org or not project:
            raise ValueError("Azure DevOps organization and project required (config or AZDO_ORG / AZDO_PROJECT).")
        wiql = cfg.get("wiql")
        max_items = int(cfg.get("max_items", 75))
        return cls(org, project, pat, wiql=wiql, max_items=max_items)

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    def fetch_bugs(self) -> list[Defect]:
        """Run WIQL, batch-get work items, map to Defect."""
        wiql_url = f"{self._base}/_apis/wit/wiql?api-version=7.1"
        r = requests.post(wiql_url, headers=self._headers(), json={"query": self.wiql}, timeout=60)
        r.raise_for_status()
        data = r.json()
        items = data.get("workItems") or []
        if not items:
            return []

        ids = [int(x["id"]) for x in items[: self.max_items]]
        if not ids:
            return []

        # Batch get details (max 200 per call)
        defects: list[Defect] = []
        chunk = 200
        for i in range(0, len(ids), chunk):
            batch = ids[i : i + chunk]
            ids_param = ",".join(str(x) for x in batch)
            url = f"{self._base}/_apis/wit/workitems?ids={ids_param}&api-version=7.1"
            wr = requests.get(url, headers=self._headers(), timeout=60)
            wr.raise_for_status()
            for w in wr.json().get("value") or []:
                defects.append(_work_item_to_defect(w))
        return defects


def _work_item_to_defect(w: dict[str, Any]) -> Defect:
    fields = w.get("fields") or {}
    wid = str(fields.get("System.Id", w.get("id", "")))
    title = str(fields.get("System.Title", ""))
    status = str(fields.get("System.State", ""))
    sev = fields.get("Microsoft.VSTS.Common.Severity")
    severity = str(sev) if sev is not None else "Unknown"
    created = fields.get("System.CreatedDate")
    from datetime import datetime
    parsed = None
    if created:
        try:
            parsed = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            parsed = None
    return Defect(id=f"ado-{wid}", title=title, severity=severity, status=status, created=parsed)
