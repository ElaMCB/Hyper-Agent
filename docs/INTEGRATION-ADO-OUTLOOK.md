# Azure DevOps + Outlook integration

Shadow is built around **Azure DevOps (ADO)** for work items and **Outlook** for calendar and mail. This doc explains what is wired today and how to go further.

---

## Azure DevOps (implemented)

### What it does

When `azure_devops.enabled` is `true` in `config/config.yaml`, the **morning brief** loads **open Bugs** from your project via the [Work Item Tracking REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/wiql/query-by-wiql). Results are merged with any bugs in `data/defects.json` (if present).

### Setup

1. **Create a PAT** in ADO: User settings → Personal access tokens.  
   - Scopes: **Work items → Read** (minimum).  
   - Store it only in `.env` as `AZDO_PAT` — never commit it.

2. **Set organization and project**  
   - In `config/config.yaml` under `azure_devops`, set `organization` and `project` (names as in the URL: `https://dev.azure.com/{organization}/{project}`).  
   - Or leave them blank and set **`AZDO_ORG`** and **`AZDO_PROJECT`** in `.env`.

3. **Enable the integration**

   ```yaml
   azure_devops:
     enabled: true
     organization: my-org    # or use AZDO_ORG
     project: MyProject      # or use AZDO_PROJECT
   ```

4. Run: `python src/main.py brief` or hit `/brief` on the API.

### Custom WIQL

If your process uses different states or types, override the query in config:

```yaml
azure_devops:
  enabled: true
  wiql: |
    SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Severity]
    FROM WorkItems
    WHERE [System.WorkItemType] = 'Bug'
    AND [System.State] IN ('Active', 'New', 'Committed')
    ORDER BY [Microsoft.VSTS.Common.Severity] ASC
```

`max_items` (default 75) caps how many bugs are fetched after the WIQL step.

### Test runs / Test Plans

The brief still uses **`data/test_runs.json`** for execution summaries. Pulling **Test Results** or **Test Plans** from ADO is a natural next step (different REST surface: `test` APIs). Same PAT often works with **Test → Read** scope added.

---

## Outlook (not wired in code yet)

Outlook is not a single REST API inside the repo; Microsoft exposes it through **Microsoft Graph**. Typical Shadow use cases:

| Goal | Graph approach | Lighter alternative |
|------|----------------|---------------------|
| **Meeting prep** (“what’s on my calendar today?”) | [Calendar events](https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview) with **Calendars.Read** (delegated) | **Power Automate**: scheduled flow, “Get events (V4)”, then HTTP POST to your Shadow `/brief` companion endpoint or email you a digest |
| **Scan mail for actions** | **Mail.Read** (delegated) + search or folder queries | Power Automate **When a new email arrives** (filtered) → append row to Excel / send to Teams |

### If you want Graph inside Python

1. Register an app in **Microsoft Entra ID** (Azure Portal → App registrations).  
2. Add **delegated** permissions: `Calendars.Read`, optionally `Mail.Read` / `Mail.ReadBasic`.  
3. Use **MSAL** (`msal` package) to acquire tokens (device code or auth code flow for personal/tenant use).  
4. Call `https://graph.microsoft.com/v1.0/me/calendar/calendarView?startDateTime=...&endDateTime=...`.

This is more setup than ADO’s PAT, but it is the standard path for “Outlook as a system.”

### Practical daily flow (Outlook without coding Graph yet)

- **Calendar**: 15-minute recurring block before your first sync; open `https://…/brief.md` or run `python src/main.py brief`.  
- **Power Automate**: Daily 7:00 → HTTP GET deployed Shadow `/brief.md` → post to a **private** Teams channel or email you (if the endpoint is secured or you accept the risk of a public brief).

---

## Security notes

- **PAT and Graph tokens** belong in `.env` or your host’s secret store, not in the repo.  
- A **public** `/brief` URL will expose bug counts/titles from ADO if ADO is enabled — use auth (API key middleware, private network, or VPN) for production.  
- Confirm your org’s policy on sending work item titles to an **LLM** if you enable `llm.enabled`.

---

## Summary

| System | In Shadow today | Next step |
|--------|------------------|-----------|
| **Azure DevOps** | Open Bugs → morning brief | Test Plans / runs API; finer WIQL per team |
| **Outlook** | Documented only | Power Automate first, or MSAL + Graph for calendar-driven prep |
