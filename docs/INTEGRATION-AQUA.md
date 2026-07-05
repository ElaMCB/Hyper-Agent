# A.Q.U.A ↔ Shadow integration

Shadow ([Hyper-Agent](https://github.com/ElaMCB/Hyper-Agent)) is the **leadership layer** for test intelligence. A.Q.U.A ([AQUA](https://github.com/ElaMCB/AQUA)) is the **uncertainty-quantified testing engine**. They connect through a shared JSON report.

## Shared schema

Both repos use the same contract:

| Repo | Path |
|------|------|
| AQUA | `schemas/aqua-report.schema.json` |
| Shadow | `schemas/aqua-report.schema.json` |

Sample report: `data/aqua-report.json` (Shadow) · `examples/aqua-report.json` (AQUA)

## Enable in Shadow

Edit `config/config.yaml`:

```yaml
integrations:
  aqua:
    enabled: true
    report_path: data/aqua-report.json
    alert_threshold: 0.75
    include_in_brief: true
    # endpoint: http://localhost:8000/aqua-report.json  # optional future API
```

Run a brief:

```bash
python src/main.py brief
```

Low-confidence A.Q.U.A scenarios (below `alert_threshold`) appear in the morning brief with impact and confidence.

## Produce a report from AQUA

From the AQUA repo (or any target repo with git history):

```bash
pip install -r requirements.txt
python -m aqua analyze --repo /path/to/repo --base main --head HEAD --output aqua-report.json
```

Copy into Shadow:

```bash
cp aqua-report.json /path/to/Hyper-Agent/data/aqua-report.json
python /path/to/Hyper-Agent/src/main.py brief
```

## Demo loop

1. Open a PR in any repo with AQUA CI (or run `aqua analyze` locally).
2. `aqua-report.json` lands in `data/` or as a CI artifact.
3. Shadow ingests it on the next `brief` or `headquarters` run.
4. Managers see low-confidence scenarios in the brief — with provenance.

See also: [AQUA deploy guide](https://github.com/ElaMCB/AQUA/blob/main/docs/DEPLOY-AQUA-SHADOW.md)
