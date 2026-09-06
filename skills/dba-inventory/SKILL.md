---
name: dba-inventory
description: Maintain the platform inventory that discovery runs feed: load runs, list platforms with open findings, track finding status and owners, export the platform table, and answer questions such as which platforms are unsupported or which High findings are open. Use after any dba-discovery run and whenever someone asks what data stores exist and how they stand.
---

# Platform inventory

The inventory is a SQLite file (`inventory/inventory.sqlite` by default, schema in `inventory/schema.sql`) with five tables: `platforms`, `databases`, `discovery_runs`, `findings`, `unknowns`, and three views: `v_latest_runs`, `v_platform_summary`, `v_open_findings`. One platform is one engine on one host and port. A run belongs to a platform; findings and unknowns belong to a run. Status lives on the finding, so the same weakness can be open on one platform and accepted on another.

## Commands

```
python -m discovery inventory load     --store inventory/inventory.sqlite --run runs/<name>
python -m discovery inventory list     --store inventory/inventory.sqlite
python -m discovery inventory findings --store inventory/inventory.sqlite [--severity High]
python -m discovery inventory status   --store inventory/inventory.sqlite --run-name <name> --code PG-BKP-001 --status in_progress --owner "platform team" --due 2026-10-15
python -m discovery inventory export   --store inventory/inventory.sqlite --out inventory/platforms.csv
```

Loading the same run twice replaces its findings and unknowns; loading a newer run for the same platform makes it the latest run, and the views report from the latest run only. Statuses: `open`, `accepted`, `in_progress`, `done`, `risk_accepted`. `done` and `risk_accepted` drop out of the open counts.

## Procedure after a discovery run

1. Load the run. Check the printed counts against the wiki page summary.
2. List platforms. Confirm the environment and owner columns are filled; if not, rerun the discovery with `--environment` and `--owner`, or update the row with SQL.
3. Export the platform table and attach it to the wiki as the platform inventory page.
4. When the owner accepts the prioritized table, set status, owner and due date on each finding with the `status` command.

## Answering questions from the inventory

Which platforms are past or near end of support: `SELECT flavour, version, host, environment FROM v_platform_summary` and read the version against the lifecycle table in `discovery/rules.py`; the INV findings in `v_open_findings` list the ones already flagged.

Which High findings are open, by owner: `SELECT owner, host, code, title, due FROM v_open_findings WHERE severity = 'High' ORDER BY owner, due`.

Which unknowns still need a human: `SELECT p.host, u.area, u.question, u.how_to_obtain FROM unknowns u JOIN v_latest_runs r ON r.id = u.run_id JOIN platforms p ON p.id = r.platform_id WHERE u.resolved = 0`.

How a platform changed between two runs: `python -m discovery diff --a runs/<earlier> --b runs/<later>` prints resolved, new and remaining findings by title (ids are numbered per run; the title is the stable key).

Total data under management: `SELECT flavour, COUNT(*) AS platforms, ROUND(SUM(size_bytes) / 1073741824.0, 1) AS gb FROM v_platform_summary GROUP BY flavour`.

## Rules

Never edit findings by hand in the wiki without updating the status in the inventory; the inventory is the record of truth for status, the wiki page for evidence. Keep run directories (`runs/<name>`) with the inventory; the `evidence_path` and `report_path` columns point at them. Refresh production platforms at least quarterly and after any major change; the `last_seen` column shows which platforms are stale. When a platform is decommissioned, keep its rows and set `environment` to `retired` so history survives.
