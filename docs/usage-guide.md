# Usage guide: discovery with Claude and the skill set

This guide is for the two people who will use the package: the DBA who runs discoveries and the manager who reads the pages and the inventory.

## Installing the skills

Copy the three folders under `skills/` into the place your Claude setup reads skills from. In Claude Code, that is `.claude/skills/` in the repository (project skills) or `~/.claude/skills/` (personal skills); each folder keeps its `SKILL.md` and `reference/` files. In the Claude apps, upload each folder as a skill from the Skills settings page. Once installed, Claude loads a skill when the request matches its description: "assess our orders database" loads `dba-discovery`; "which platforms have open High findings" loads `dba-inventory`; "prepare the review for the shop database" loads `dba-review`.

## A first discovery, step by step

1. Ask the owner for a read only account using the grant script in `skills/dba-discovery/reference/postgres-access.md` or `mysql-access.md`.
2. Open Claude in the repository and ask: "Run a discovery of the orders platform, PostgreSQL at db1.internal port 5432 database orders, production, owned by the orders team, using the discovery account." Claude follows the `dba-discovery` procedure: it runs `python -m discovery run ...`, reads the findings and the appendix, asks you the interview questions, edits the page, loads the inventory.
3. Read `runs/<name>/wiki.md`. Section 1 tells you what is there and what to do first; section 4 is the plan; the appendix is the proof.
4. Paste the page into the wiki. Attach `inventory/platforms.csv` as the platform inventory page.
5. Book the review with the owner and use `dba-review`.

## What to expect in the page

A single production PostgreSQL server without a standby or WAL archiving produces two High findings (no replica, no point in time recovery) before anything else is considered, because those are the two ways to lose data or the service. A MariaDB server with `log_bin` off and TLS disabled produces the equivalent pair plus the TLS finding. Everything else ranks below those. Unknowns are normal: the backup schedule and the last restore test are always a human answer.

## Reading the inventory

`python -m discovery inventory list` prints one line per platform: engine, version, host, environment, owner, database count, size, the latest run, and the open counts by severity. `python -m discovery inventory findings --severity High` prints the open High findings across every platform with owner and due date. `python -m discovery inventory export` writes the platform table as CSV for the wiki or a spreadsheet.

## Working without a network path to the server

Some platforms cannot be reached from the machine that runs Claude. Give the owner the query catalogue from the reference file; they run the queries in their console and paste the results into `evidence.json` under the same keys; `python -m discovery assess --run runs/<name>` produces the page from the file. The page is identical in structure, and the evidence keys still cite what was run.

## Keeping it honest

The rules only say what the evidence supports. When you disagree with a severity, change it on the page and write why next to it; do not change the rule for one platform, because comparability across platforms is the point. When a finding is wrong, remove it and record the reason in the review section. When the owner accepts a risk, record `risk_accepted` with the reason, so the next reviewer does not raise it again without new evidence.

## Cadence

Production platforms: a run every quarter, after every major change, and before any handover. Other environments: before audits and handovers. After each run, `python -m discovery diff` gives the three numbers to report: resolved, new, remaining.
