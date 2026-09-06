---
name: dba-discovery
description: Run an evidence based discovery of a PostgreSQL or MySQL or MariaDB platform across ten review areas and write the wiki page with findings, unknowns and prioritized recommendations. Use when asked to assess, audit, review, document or onboard a database platform, or when a new data store appears in the inventory.
---

# Database platform discovery

You are conducting a structured discovery of one database platform. The output is one wiki page per platform that a manager can act on and an engineer can verify. Every statement on the page is backed by a query and its result, or is listed as an unknown with the way to obtain it. You never guess, and you never write a finding you cannot point to evidence for.

## When to use this skill

Use it when the request is any of: assess or audit a database, document a platform we inherited, prepare a handover, review a vendor or team's database setup, produce a risk register for a data store, or refresh the discovery of a platform already in the inventory. If the request is about a single query or a single incident, this skill is too heavy; answer directly.

## The ten review areas

Work through all ten, in this order, for every platform. `reference/areas.md` gives the questions each area must answer, the evidence keys that answer them and what good looks like.

1. Database and platform inventory: what exists (engine, version, support status, databases, sizes, extensions, core settings).
2. Architecture and data flow: role of this server, connections by application, largest objects, replication topology, foreign links.
3. High availability and disaster recovery: replicas, lag, sync mode, slots, WAL or binlog settings, failover procedure.
4. Database change management and release processes: how schema changes reach the server, migration tooling, DDL logging.
5. Security configuration and encryption: transport encryption, authentication methods, network exposure, password hashing.
6. User access and authentication: superusers and privileged accounts, expiry, host restrictions, public schema, anonymous accounts.
7. Backup and retention policies: archiving or binlog for point in time recovery, backup jobs, retention, restore tests.
8. Cloud cost and resource usage: cache efficiency, unused indexes, bloat, connection headroom, buffer pool versus data size.
9. Monitoring and observability: slow statement logging, statement statistics, timing instrumentation, log collection.
10. Outstanding database concerns and operational issues: wraparound or transaction id age, invalid indexes, tables without primary keys, storage engines, long running statements, lock waits.

## Procedure

### 1. Intake

Establish, before touching the server: platform name and environment (production, staging, development), business owner and technical owner, the engine and version the owner believes is running, how you will connect (host, port, database, credentials for a read only account), the change window if any, and the reason for the discovery (handover, audit, incident follow up, routine refresh). Record these in the run command's `--name`, `--environment` and `--owner` values. If the owner cannot answer a question, note it; the unknown list is part of the deliverable.

### 2. Access

Request a read only account with the grants in `reference/postgres-access.md` or `reference/mysql-access.md`. Do not run discovery with a superuser or root unless the owner insists and the session is supervised; the collectors are read only either way, but the report should demonstrate least privilege. If a grant is refused, proceed anyway: every check that fails for lack of permission becomes an unknown with the exact grant needed, and the page says so.

### 3. Collect

Run the collector once per platform from the repository root:

```
python -m discovery run --engine postgres --dsn postgresql://discovery:PASSWORD@host:5432/dbname --name prod-orders-pg --environment production --owner "orders team"
python -m discovery run --engine mysql --dsn mysql://discovery:PASSWORD@host:3306/dbname --name prod-shop-mysql --environment production --owner "shop team"
```

The run writes `runs/<name>/evidence.json` (every query and its rows), `findings.json`, `run.json` and `wiki.md`. The DSN never reaches any output file. When the collector cannot be run (no network path from your machine, a managed service that blocks the account), execute the queries in the reference files by hand through the owner's console and paste the results into the evidence file using the same keys; the rules and the page work from the file, not from the connection.

### 4. Assess

Read `findings.json` and the appendix of `wiki.md` yourself. The rules are deliberate but not omniscient. For each finding, confirm the evidence supports the sentence exactly as written; delete or reword any finding the evidence does not carry. Then look for what the rules could not see: application patterns in `architecture.connections`, sizes that do not match the owner's expectation, extensions that imply hidden dependencies, roles whose names reveal shared credentials. Add those as findings by hand in the same format (id, area, severity, title, what the evidence shows, recommendation, effort, evidence keys), quoting the evidence key.

Severity scale: High means data loss, outage or breach is plausible without action; Medium means a real weakness with a workaround or a delayed impact; Low means hygiene, cost or convenience; Info is context only. Effort: Small is a setting or a grant within a day, Medium is a task of days with a change window, Large is a project.

### 5. Interview

Ask the owner the questions in `reference/interview.md` for the things a server cannot report: backup schedule and retention, last restore test, recovery time and recovery point objectives, on call and escalation, how changes are approved, licensing and hosting cost lines, and known pain. Every answer becomes evidence quoted as `interview.<topic>` in the page; every unanswered question stays in the unknown list.

### 6. Write the page

The page is generated by the run and then edited by you. Keep the structure from `reference/wiki-template.md`: summary, findings by area, unknowns with how to obtain them, prioritized recommendations, evidence appendix. Writing rules: plain sentences, no hedging words where the evidence is clear, no adjectives without a number, the evidence key after every claim, one recommendation per finding with an effort label, and the owner's answers quoted rather than paraphrased. Do not delete rows from the appendix; the appendix is what makes the page verifiable.

### 7. Record

Load the run into the inventory (see the `dba-inventory` skill) and export the platform table. Send the page to the owner with the top five actions in the message body.

### 8. Review and repeat

Walk the prioritized table with the owner, set a status, owner and due date on each finding, and agree the refresh cadence (quarterly for production, after any major change, and always before a handover). On the next run, use `python -m discovery diff` to report what was resolved, what is new and what remains.

## Evidence rules

Every finding cites at least one evidence key in the form `area.key`; the key must exist in the appendix. Numbers in the text come from the rows, not from memory. If a query failed, the page shows the failure and the grant that fixes it; the finding that depends on it is not written. Statistics based findings (cache hit, unused indexes, dead rows) state the statistics window (`stats_reset` or server uptime) because a short window proves little. Version and support dates come from the lifecycle table in `discovery/rules.py`, which names its sources and the date it was checked; confirm on the vendor page before recommending an upgrade.

## Unknown handling

An unknown is a question the discovery could not answer. It has three parts: the question, why it could not be answered (permission, feature absent, needs a human) and exactly how to obtain the answer (the grant, the command, the person). Unknowns are listed in their area and again in section 3 of the page. A page with zero unknowns on a real platform is suspicious; backups and restore tests always need a human answer.

## Quality gates before delivery

The page has all four numbered sections and the appendix; every finding id is unique and appears in the prioritized table; every evidence key cited exists in the appendix; the summary table has version, role, database count and size, connections and replica count; the top five actions read as instructions a team can start on Monday; no password, DSN or token appears anywhere in the page; the run is loaded in the inventory and the platform row shows the right environment and owner; the owner has been asked the interview questions and their answers or the unknowns are on the page.

## Output

Deliver `runs/<name>/wiki.md` (paste into the wiki as one page), the platform row in the inventory, and the top five actions in the message to the owner. Keep `evidence.json` with the run; it is the audit trail.
