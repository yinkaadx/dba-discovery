# dba-discovery: a Claude skill set and inventory for database platform discovery

A repeatable, evidence based discovery process for PostgreSQL and MySQL or MariaDB. Three Claude skills describe the process; a small Python package does the collecting, assessing and reporting; a SQLite inventory keeps the platform list and the status of every finding.

```
skills/
  dba-discovery/SKILL.md          the procedure: intake, access, collect, assess, interview, write, record, review
  dba-discovery/reference/        the ten review areas, least privilege access scripts, the full query catalogue,
                                  interview questions, the wiki template and writing rules
  dba-inventory/SKILL.md          loading runs, listing platforms, tracking status, exporting, answering questions
  dba-review/SKILL.md             the review meeting, remediation plan, status reports, repeat discovery
discovery/                        collectors (read only), rules, report renderer, inventory store, command line
inventory/schema.sql              the inventory tables and views
docs/                             sample wiki pages produced against live servers, the usage guide, the evidence log
tests/                            20 checks: rules, page structure, inventory round trip, command line, live end to end
```

## Ten review areas

Database and platform inventory; architecture and data flow; high availability and disaster recovery; database change management and release processes; security configuration and encryption; user access and authentication; backup and retention policies; cloud cost and resource usage; monitoring and observability; outstanding database concerns and operational issues. `skills/dba-discovery/reference/areas.md` states the questions each area answers, the evidence that answers them, what good looks like, and the thresholds applied.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m discovery run --engine postgres --dsn postgresql://discovery:PASSWORD@host:5432/app --name prod-app-pg --environment production --owner "app team"
python -m discovery run --engine mysql    --dsn mysql://discovery:PASSWORD@host:3306/shop   --name prod-shop-mysql --environment production --owner "shop team"
python -m discovery inventory load --run runs/prod-app-pg
python -m discovery inventory list
```

Each run writes `runs/<name>/evidence.json` (every query with its rows or its error), `findings.json`, `run.json` and `wiki.md`, the page to paste into the wiki. The read only accounts and their grants are in `skills/dba-discovery/reference/postgres-access.md` and `mysql-access.md`; they were tested on PostgreSQL 16 and MariaDB 10.11.

## What a page contains

A summary table (version, role, databases and size, connections, replicas), the finding counts by severity, the top five actions, findings by area with the evidence key behind every sentence, the unknowns with exactly how to obtain each answer, a prioritized table (severity first, smallest effort first), and an appendix with every query and its result. See `docs/sample-wiki-postgres.md` and `docs/sample-wiki-mysql.md`, produced against live servers.

## Design choices

Read only by construction: the collectors only select from catalogues, statistics views and settings; no application table is read. Tolerant by construction: a query that fails for lack of a grant or a version difference becomes an unknown that names the grant, never a crash and never a guess. Verifiable by construction: the page cites an evidence key for every claim and the appendix holds the query, so a sceptical engineer can rerun it. Comparable by construction: the same rules and thresholds apply to every platform, so two pages can be read side by side and a repeat run can be diffed (`python -m discovery diff`).

## Adapting

Thresholds and severities live in `discovery/rules.py`, one small function per engine; lifecycle dates sit at the top of the file with their sources and the date they were checked. New evidence is one line in a collector plus one rule; `python tools/render_queries.py` regenerates the query catalogue in the skill references so the documents never drift from the code. The inventory is SQLite so it needs nothing installed; the schema is plain enough to move to PostgreSQL if the wiki should read from a shared database.

## Tests

`python -m pytest -v` runs 18 checks without a server. Set `DISCOVERY_PG_DSN` and `DISCOVERY_MYSQL_DSN` to run the two live end to end checks as well. `docs/evidence.md` holds the output of all 20 and a complete command line session.
