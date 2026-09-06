"""Turn collected evidence into findings.

Every finding names the evidence key it was derived from, so a reader can open
the appendix, see the exact query and rows, and rerun the query themselves.
Rules never guess: when the evidence is missing (permission denied, feature not
present on that version) the rule records an unknown with the way to obtain it
instead of a finding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date

SEVERITIES = ["High", "Medium", "Low", "Info"]
EFFORTS = ["Small", "Medium", "Large"]

# Vendor lifecycle dates, checked on 2026-09-06 against postgresql.org/support/versioning, mariadb.org/about (community end of life)
# and Oracle's lifetime support schedule as summarised on endoflife.date/mysql. PostgreSQL: final minor release of the line.
# MySQL: end of extended support (9.7 LTS: end of premier support, the earlier and safer date). Verify before acting on a date.
PG_EOL = {10: date(2022, 11, 10), 11: date(2023, 11, 9), 12: date(2024, 11, 21), 13: date(2025, 11, 13), 14: date(2026, 11, 12),
          15: date(2027, 11, 11), 16: date(2028, 11, 9), 17: date(2029, 11, 8), 18: date(2030, 11, 14)}
MYSQL_EOL = {"5.6": date(2021, 2, 28), "5.7": date(2023, 10, 31), "8.0": date(2026, 4, 30), "8.4": date(2032, 4, 30), "9.7": date(2034, 4, 21)}
MARIADB_EOL = {"10.3": date(2023, 5, 25), "10.4": date(2024, 6, 18), "10.5": date(2025, 6, 24), "10.6": date(2026, 7, 6),
               "10.11": date(2028, 2, 16), "11.4": date(2029, 5, 29), "11.8": date(2028, 6, 4), "12.3": date(2029, 6, 12)}


@dataclass
class Finding:
    id: str
    area: str
    severity: str
    title: str
    detail: str
    recommendation: str
    effort: str
    evidence: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


@dataclass
class Unknown:
    area: str
    question: str
    how_to_obtain: str
    evidence: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


class RuleContext:
    def __init__(self, ev: dict, prefix: str, today: date | None = None):
        self.ev = ev
        self.prefix = prefix
        self.today = today or date.today()
        self.findings: list[Finding] = []
        self.unknowns: list[Unknown] = []
        self._counters: dict[str, int] = {}

    # evidence helpers
    def block(self, area, key):
        return self.ev.get(area, {}).get(key)

    def rows(self, area, key):
        b = self.block(area, key)
        if not b or not b.get("ok"):
            return None
        return b["rows"]

    def setting(self, area, key, name):
        rows = self.rows(area, key)
        if rows is None:
            return None
        for r in rows:
            n = r.get("name") or r.get("Variable_name")
            if n and n.lower() == name.lower():
                return str(r.get("setting") if "setting" in r else r.get("Value"))
        return None

    # recording helpers
    def add(self, area, severity, title, detail, recommendation, effort, evidence):
        code = {"inventory": "INV", "architecture": "ARC", "ha_dr": "HA", "change_management": "CHG", "security": "SEC", "access": "ACC",
                "backup": "BKP", "cost": "CST", "monitoring": "MON", "operations": "OPS"}[area]
        n = self._counters.get(code, 0) + 1
        self._counters[code] = n
        assert severity in SEVERITIES and effort in EFFORTS
        self.findings.append(Finding(f"{self.prefix}-{code}-{n:03d}", area, severity, title, detail, recommendation, effort, list(evidence)))

    def unknown(self, area, question, how, evidence=()):
        self.unknowns.append(Unknown(area, question, how, list(evidence)))

    def require(self, area, key, question, how):
        """Return rows, or record an unknown and return None."""
        rows = self.rows(area, key)
        if rows is None:
            b = self.block(area, key)
            err = (b or {}).get("error", "not collected")
            self.unknown(area, question, f"{how} (collector result: {err})", [f"{area}.{key}"])
        return rows


def _major_pg(version_text: str) -> int | None:
    m = re.search(r"(\d+)(?:\.(\d+))?", version_text or "")
    return int(m.group(1)) if m else None


def _months_between(a: date, b: date) -> float:
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30.0


def _lifecycle(ctx: RuleContext, area, label, eol: date | None, evidence):
    if eol is None:
        ctx.unknown(area, f"Support status of {label}", "Check the vendor lifecycle page for this release line", evidence)
        return
    months = _months_between(ctx.today, eol)
    if months < 0:
        ctx.add(area, "High", f"{label} is past end of support", f"Vendor support ended on {eol.isoformat()}; no further security fixes are published for this line.",
                "Plan an upgrade to a supported release line, starting with a restore of the latest backup into a test environment and an application regression pass.", "Large", evidence)
    elif months < 12:
        ctx.add(area, "Medium", f"{label} reaches end of support within a year", f"Vendor support ends on {eol.isoformat()}.",
                "Schedule the major version upgrade in the next two quarters while the current line still receives fixes.", "Large", evidence)


# ---------------------------------------------------------------- PostgreSQL
def assess_postgres(ev: dict, today: date | None = None):
    ctx = RuleContext(ev, "PG", today)
    # inventory and lifecycle
    ver = ctx.require("inventory", "version", "Server version and start time", "Run SELECT version() as any role")
    if ver:
        major = _major_pg(ver[0].get("server_version", ""))
        _lifecycle(ctx, "inventory", f"PostgreSQL {major}", PG_EOL.get(major), ["inventory.version"])
    # architecture and high availability
    rec = ctx.rows("architecture", "role")
    in_recovery = bool(rec and rec[0].get("in_recovery"))
    rep = ctx.require("ha_dr", "replication", "Streaming replicas attached to this primary", "Grant pg_monitor to the discovery role and rerun SELECT * FROM pg_stat_replication")
    wal_level = ctx.setting("ha_dr", "settings", "wal_level")
    if rep is not None and not in_recovery and len(rep) == 0:
        ctx.add("ha_dr", "High", "Single primary with no streaming replica", "pg_stat_replication returned no rows and the server is not in recovery, so a host failure means downtime until a restore completes.",
                "Add a hot standby (streaming replication with a replication slot) and a tested promotion procedure; decide the target recovery time with the business first.", "Large", ["ha_dr.replication", "architecture.role"])
    if rep:
        sync = ctx.setting("ha_dr", "settings", "synchronous_standby_names") or ""
        if sync.strip() == "":
            ctx.add("ha_dr", "Low", "Replication is asynchronous", f"{len(rep)} replica(s) attached but synchronous_standby_names is empty, so the last committed transactions can be lost on failover.",
                    "Keep asynchronous replication if the recovery point objective allows seconds of loss; otherwise name a synchronous standby and accept the commit latency.", "Small", ["ha_dr.replication", "ha_dr.settings"])
        for r in rep:
            if r.get("state") not in (None, "streaming"):
                ctx.add("ha_dr", "Medium", f"Replica {r.get('client_addr')} is in state {r.get('state')}", "A replica that is not streaming is catching up or stuck and cannot be promoted safely.",
                        "Check the replica log and network path, then confirm replay lag returns to near zero.", "Small", ["ha_dr.replication"])
    if wal_level == "minimal":
        ctx.add("ha_dr", "High", "wal_level is minimal", "With wal_level minimal neither streaming replication nor WAL archiving for point in time recovery is possible.",
                "Set wal_level to replica (restart required) before enabling archiving or adding a standby.", "Small", ["ha_dr.settings"])
    slots = ctx.rows("ha_dr", "slots")
    if slots:
        for s in slots:
            if not s.get("active"):
                ctx.add("ha_dr", "Medium", f"Inactive replication slot {s.get('slot_name')} retains WAL", f"The slot is inactive and holds {s.get('retained_wal')} of WAL, which grows until the disk fills.",
                        "Drop the slot if its consumer is gone, or reconnect the consumer; set max_slot_wal_keep_size as a safety limit.", "Small", ["ha_dr.slots"])
    # backup and point in time recovery
    archive_mode = ctx.setting("backup", "settings", "archive_mode")
    if archive_mode is not None and archive_mode != "on":
        ctx.add("backup", "High", "WAL archiving is off", "archive_mode is off, so point in time recovery is not possible from this server; recovery is limited to the last full backup taken by external tooling.",
                "Enable archive_mode with an archive_command or a backup tool that manages WAL (pgBackRest, Barman, or the cloud provider's PITR), then run a timed restore test.", "Medium", ["backup.settings"])
    arch = ctx.rows("backup", "archiver")
    if arch and archive_mode == "on":
        a0 = arch[0]
        if (a0.get("failed_count") or 0) > 0 and a0.get("last_failed_time") and (a0.get("last_archived_time") is None or str(a0["last_failed_time"]) > str(a0["last_archived_time"])):
            ctx.add("backup", "High", "WAL archiving is failing", f"pg_stat_archiver shows {a0.get('failed_count')} failures and the last failure is more recent than the last success ({a0.get('last_failed_wal')}).",
                    "Fix the archive_command target (permissions, disk, credentials) now; until it succeeds, WAL accumulates in pg_wal and PITR has a gap.", "Small", ["backup.archiver"])
    ctx.unknown("backup", "Backup schedule, retention and the date of the last successful restore test",
                "Ask the operations owner for the backup job definition, retention policy and restore test log; the database cannot report these", ["backup.backup_tooling_note"])
    # change management
    mig = ctx.require("change_management", "migration_tables", "Schema migration tool in use", "Grant SELECT on information_schema.tables or ask the application team which migration tool they use")
    if mig is not None and len(mig) == 0:
        ctx.add("change_management", "Medium", "No schema migration history table found", "None of the common migration tools (Flyway, Liquibase, Alembic, Django, Prisma, Knex, goose, EF) left a history table, so schema changes are probably applied by hand.",
                "Adopt one migration tool and put every DDL change in version control with a review step; start by baselining the current schema.", "Medium", ["change_management.migration_tables"])
    log_statement = ctx.setting("change_management", "ddl_logging", "log_statement")
    evt = ctx.rows("change_management", "event_triggers")
    if log_statement in ("none",) and evt is not None and len(evt) == 0:
        ctx.add("change_management", "Low", "DDL is not logged", "log_statement is none and there are no event triggers, so there is no record of who changed the schema and when.",
                "Set log_statement to ddl (no restart needed) so every schema change lands in the server log.", "Small", ["change_management.ddl_logging", "change_management.event_triggers"])
    # security
    ssl = ctx.setting("security", "ssl", "ssl")
    listen = ctx.setting("security", "ssl", "listen_addresses") or ""
    if ssl == "off" and listen not in ("localhost", "127.0.0.1", ""):
        ctx.add("security", "High", "TLS is off for network connections", f"ssl is off while listen_addresses is {listen}, so credentials and data cross the network in clear text.",
                "Install a certificate, set ssl on, and require TLS in pg_hba (hostssl rows) for every non local client.", "Small", ["security.ssl"])
    pw = ctx.setting("security", "ssl", "password_encryption")
    if pw == "md5":
        ctx.add("security", "Medium", "Passwords are hashed with md5", "password_encryption is md5; `scram-sha-256` is the supported stronger method.",
                "Set password_encryption to `scram-sha-256`, reset each password so the new hash is stored, then change pg_hba md5 rows to `scram-sha-256`.", "Medium", ["security.ssl"])
    hba = ctx.require("security", "hba", "Client authentication rules (pg_hba.conf)", "In this database run GRANT EXECUTE ON FUNCTION pg_hba_file_rules() TO discovery and rerun; on a managed service attach the network and authentication settings instead")
    if hba:
        trust = [r for r in hba if r.get("auth_method") == "trust" and r.get("type") != "local"]
        if trust:
            ctx.add("security", "High", "Network clients can connect without a password", f"{len(trust)} pg_hba rule(s) use trust for host connections (lines {', '.join(str(r['line_number']) for r in trust)}).",
                    "Replace trust with `scram-sha-256` (or certificate authentication) on every host rule.", "Small", ["security.hba"])
        wide = [r for r in hba if r.get("type") in ("host", "hostssl", "hostnossl") and any(x in ("0.0.0.0/0", "::/0", "all") for x in (r.get("address") or []))]
        if wide:
            ctx.add("security", "Medium", "Authentication rules accept any source address", f"{len(wide)} rule(s) match every address; the network firewall is the only barrier.",
                    "Narrow the address column to the application subnets and the bastion host.", "Small", ["security.hba"])
        md5 = [r for r in hba if r.get("auth_method") == "md5"]
        if md5 and pw != "md5":
            ctx.add("security", "Low", "Some pg_hba rules still use md5", f"{len(md5)} rule(s) authenticate with md5 while the server hashes new passwords with {pw}.",
                    "Change those rules to `scram-sha-256` after the affected passwords have been reset.", "Small", ["security.hba"])
    sslc = ctx.rows("security", "ssl_connections")
    if sslc and ssl == "on":
        plain = sum(r.get("n", 0) for r in sslc if r.get("ssl") is False)
        if plain:
            ctx.add("security", "Low", "Some sessions are connected without TLS", f"{plain} current session(s) are not using TLS although the server supports it.",
                    "Move those clients to sslmode=require and convert their pg_hba rows to hostssl.", "Small", ["security.ssl_connections"])
    # access
    roles = ctx.require("access", "roles", "Role list with superuser and login flags", "Grant SELECT on pg_roles (normally readable by everyone) and rerun")
    if roles:
        supers = [r["rolname"] for r in roles if r.get("rolsuper") and r["rolname"] != "postgres"]
        if supers:
            ctx.add("access", "Medium", "Additional superuser roles exist", f"Superuser is held by {', '.join(supers)} besides postgres; a superuser can read every table and run OS level functions.",
                    "Replace superuser with the specific privileges each role needs (pg_read_all_data, pg_monitor, CREATEDB) and keep one break glass superuser with a vaulted password.", "Medium", ["access.roles"])
        login_no_limit = [r["rolname"] for r in roles if r.get("rolcanlogin") and r.get("rolvaliduntil") is None and not r.get("rolsuper")]
        if login_no_limit:
            ctx.add("access", "Low", "Login roles have no password expiry", f"{len(login_no_limit)} login role(s) have no VALID UNTIL date: {', '.join(login_no_limit[:8])}.",
                    "Decide a rotation period for human accounts and set VALID UNTIL; keep service accounts on vault managed rotation.", "Small", ["access.roles"])
        bypass = [r["rolname"] for r in roles if r.get("rolbypassrls") and not r.get("rolsuper")]
        if bypass:
            ctx.add("access", "Low", "Roles bypass row level security", f"{', '.join(bypass)} have BYPASSRLS.", "Confirm each one needs it; remove it from application roles.", "Small", ["access.roles"])
    pub = ctx.rows("access", "public_schema")
    if pub:
        acl = str(pub[0].get("nspacl") or "")
        if re.search(r"(^|[{,])=UC/", acl):
            ctx.add("access", "Medium", "Any role can create objects in the public schema", "The public schema grants CREATE to PUBLIC (pre PostgreSQL 15 default), which allows object shadowing attacks.",
                    "REVOKE CREATE ON SCHEMA public FROM PUBLIC and give application roles their own schema.", "Small", ["access.public_schema"])
    # cost and capacity
    cache = ctx.rows("cost", "cache_hit")
    if cache:
        for r in cache:
            pct = r.get("cache_hit_pct")
            if pct is not None and float(pct) < 90 and (r.get("blks_read") or 0) > 100000:
                ctx.add("cost", "Medium", f"Low buffer cache hit ratio in {r['datname']}", f"Cache hit is {pct} percent over {r['blks_read']} block reads since {r.get('stats_reset')}.",
                        "Check shared_buffers against the working set and the largest tables' access patterns before buying memory.", "Medium", ["cost.cache_hit"])
            if (r.get("deadlocks") or 0) > 0:
                ctx.add("cost", "Low", f"Deadlocks recorded in {r['datname']}", f"{r['deadlocks']} deadlock(s) since {r.get('stats_reset')}.",
                        "Enable log_lock_waits and review the application's lock ordering for the tables involved.", "Small", ["cost.cache_hit"])
    unused = ctx.rows("cost", "unused_indexes")
    if unused:
        ctx.add("cost", "Low", f"{len(unused)} index(es) have never been scanned", "Indexes with zero scans since statistics reset cost write time and disk: " + ", ".join(f"{r['index']} ({r['size']})" for r in unused[:6]) + ".",
                "Confirm the statistics window covers a full business cycle, then drop the unused ones with DROP INDEX CONCURRENTLY.", "Small", ["cost.unused_indexes"])
    dead = ctx.rows("cost", "dead_tuples")
    if dead:
        bloated = [r for r in dead if (r.get("n_dead_tup") or 0) > 10000 and r.get("dead_pct") is not None and float(r["dead_pct"]) > 20]
        if bloated:
            ctx.add("cost", "Medium", "Tables carry a high share of dead rows", "; ".join(f"{r['relname']} {r['dead_pct']} percent dead ({r['n_dead_tup']} rows)" for r in bloated[:5]),
                    "Lower autovacuum_vacuum_scale_factor for these tables and check that autovacuum keeps up; consider pg_repack for the largest.", "Medium", ["cost.dead_tuples"])
    cvm = ctx.rows("cost", "connections_vs_max")
    if cvm:
        cur, mx = cvm[0].get("current_connections") or 0, cvm[0].get("max_connections") or 1
        if cur / mx > 0.8:
            ctx.add("cost", "High", "Connection count is near max_connections", f"{cur} of {mx} connections in use.", "Add a connection pooler (PgBouncer) in transaction mode before raising max_connections.", "Medium", ["cost.connections_vs_max"])
        elif mx > 500:
            ctx.add("cost", "Low", "max_connections is high", f"max_connections is {mx}; each connection costs memory and scheduling even when idle.",
                    "Introduce a pooler and bring max_connections down to a few hundred.", "Medium", ["cost.connections_vs_max"])
    # monitoring
    pss = ctx.rows("monitoring", "pg_stat_statements")
    if pss is not None and (pss[0].get("installed") or 0) == 0:
        ctx.add("monitoring", "Medium", "pg_stat_statements is not installed", "Without it there is no per query view of time, calls and I/O, so slow query work is guesswork.",
                "Add pg_stat_statements to shared_preload_libraries (restart) and CREATE EXTENSION it in each database.", "Small", ["monitoring.pg_stat_statements"])
    lmds = ctx.setting("monitoring", "settings", "log_min_duration_statement")
    if lmds == "-1":
        ctx.add("monitoring", "Medium", "Slow statements are not logged", "log_min_duration_statement is `-1`, so no statement is ever written to the log by duration.",
                "Set log_min_duration_statement to a value such as 1000 ms (no restart) and review the log weekly.", "Small", ["monitoring.settings"])
    if ctx.setting("monitoring", "settings", "autovacuum") == "off":
        ctx.add("monitoring", "High", "autovacuum is off", "Dead rows and transaction id age grow unchecked; the server will eventually refuse writes to protect against wraparound.",
                "Turn autovacuum on immediately and run a manual VACUUM on the oldest databases.", "Small", ["monitoring.settings"])
    for name, sev, why in (("track_io_timing", "Low", "I/O time per query is not recorded"), ("log_checkpoints", "Low", "checkpoint timing is not logged"), ("log_lock_waits", "Low", "lock waits over deadlock_timeout are not logged")):
        if ctx.setting("monitoring", "settings", name) == "off":
            ctx.add("monitoring", sev, f"{name} is off", f"{why}, which removes a cheap diagnostic.", f"Set {name} to on; the cost is negligible on modern hardware.", "Small", ["monitoring.settings"])
    if ctx.setting("monitoring", "settings", "logging_collector") == "off" and "syslog" not in (ctx.setting("monitoring", "settings", "log_destination") or ""):
        ctx.add("monitoring", "Info", "Server log relies on the service wrapper", "logging_collector is off and log_destination is not syslog; on Debian and Ubuntu packages the cluster wrapper captures stderr into /var/log/postgresql, on other installs the lines may be lost.",
                "Confirm where the log lands and that it rotates; otherwise enable logging_collector with daily rotation or route to syslog or the cloud log service.", "Small", ["monitoring.settings"])
    # operations
    wrap = ctx.rows("operations", "wraparound")
    if wrap:
        for r in wrap:
            pct = float(r.get("pct_of_limit") or 0)
            if pct > 80:
                ctx.add("operations", "High", f"Transaction id age in {r['datname']} is {pct} percent of the freeze limit", "Forced anti wraparound vacuum is imminent and can stall the database.",
                        "Run VACUUM FREEZE on the oldest tables now and check autovacuum workers and cost limits.", "Small", ["operations.wraparound"])
            elif pct > 50:
                ctx.add("operations", "Medium", f"Transaction id age in {r['datname']} is {pct} percent of the freeze limit", "Autovacuum will start anti wraparound vacuums on large tables soon.",
                        "Check that autovacuum is keeping up on the biggest tables and schedule a manual VACUUM FREEZE in a quiet window.", "Small", ["operations.wraparound"])
    inv = ctx.rows("operations", "invalid_indexes")
    if inv:
        ctx.add("operations", "Medium", f"{len(inv)} invalid index(es) exist", "Invalid indexes are maintained on writes but never used for reads: " + ", ".join(f"{r['nspname']}.{r['relname']}" for r in inv[:6]) + ".",
                "REINDEX INDEX CONCURRENTLY each one, or drop it if it came from a failed build.", "Small", ["operations.invalid_indexes"])
    nopk = ctx.rows("operations", "tables_without_pk")
    if nopk:
        ctx.add("operations", "Low", f"{len(nopk)} table(s) have no primary key", "Tables without a primary key cannot be logically replicated by default and make upserts and deduplication awkward: " + ", ".join(f"{r['schema']}.{r['table']}" for r in nopk[:6]) + ".",
                "Add a surrogate or natural primary key to each, starting with the largest.", "Small", ["operations.tables_without_pk"])
    lr = ctx.rows("operations", "long_running")
    if lr:
        ctx.add("operations", "Low", f"{len(lr)} statement(s) running longer than five minutes at collection time", "; ".join(f"pid {r['pid']} ({r['usename']}) {r['running_for']}" for r in lr[:4]),
                "Identify whether these are expected batch jobs; set statement_timeout for application roles and idle_in_transaction_session_timeout.", "Small", ["operations.long_running"])
    return ctx


# ---------------------------------------------------------------- MySQL and MariaDB
def _mysql_line(version: str, flavour: str):
    v = version or ""
    is_maria = "mariadb" in (v + " " + (flavour or "")).lower()
    m = re.match(r"(\d+)\.(\d+)", v)
    if not m:
        return is_maria, None
    return is_maria, f"{m.group(1)}.{m.group(2)}"


def assess_mysql(ev: dict, today: date | None = None):
    ctx = RuleContext(ev, "MY", today)
    ver = ctx.require("inventory", "version", "Server version", "Run SELECT VERSION() as any user")
    is_maria = False
    if ver:
        is_maria, line = _mysql_line(ver[0].get("version", ""), ver[0].get("flavour", ""))
        label = f"{'MariaDB' if is_maria else 'MySQL'} {line}"
        table = MARIADB_EOL if is_maria else MYSQL_EOL
        _lifecycle(ctx, "inventory", label, table.get(line), ["inventory.version"])
    # high availability and durability
    log_bin = ctx.setting("ha_dr", "binlog", "log_bin")
    if log_bin is not None and log_bin.upper() == "OFF":
        ctx.add("ha_dr", "High", "Binary logging is off", "log_bin is OFF, so replication cannot be set up and point in time recovery between backups is impossible.",
                "Enable log_bin with binlog_format ROW, set an expiry (binlog_expire_logs_seconds or expire_logs_days) and sync_binlog 1; restart required.", "Small", ["ha_dr.binlog"])
    rep = ctx.require("ha_dr", "replica_status", "Replica status of this server", "Grant REPLICATION CLIENT (MySQL) or REPLICA MONITOR (MariaDB 10.5 and later) to the discovery user and rerun SHOW REPLICA STATUS")
    attached = ctx.rows("ha_dr", "replicas_connected")
    n_attached = (attached[0].get("replicas") if attached else None)
    if rep is not None and len(rep) == 0 and (n_attached == 0):
        ctx.add("ha_dr", "High", "Single server with no replica", "SHOW REPLICA STATUS is empty and no replica is connected, so a host failure means downtime until a restore completes.",
                "Add a replica (asynchronous or semi synchronous) and a documented promotion procedure; agree the recovery time objective with the business first.", "Large", ["ha_dr.replica_status", "ha_dr.replicas_connected"])
    if rep:
        r = rep[0]
        io = r.get("Replica_IO_Running") or r.get("Slave_IO_Running")
        sql = r.get("Replica_SQL_Running") or r.get("Slave_SQL_Running")
        lag = r.get("Seconds_Behind_Source") or r.get("Seconds_Behind_Master")
        if io != "Yes" or sql != "Yes":
            ctx.add("ha_dr", "High", "Replication threads are not running", f"IO thread {io}, SQL thread {sql}; the replica is drifting away from the primary.",
                    "Read the replica error (Last_IO_Error, Last_SQL_Error), fix the cause, and restart replication; rebuild the replica if the binlog position is gone.", "Medium", ["ha_dr.replica_status"])
        elif lag is not None and int(lag) > 60:
            ctx.add("ha_dr", "Medium", f"Replica lag is {lag} seconds", "A lagging replica cannot serve fresh reads and lengthens failover.", "Check replica hardware, parallel replication settings and long transactions on the primary.", "Medium", ["ha_dr.replica_status"])
    sync_binlog = ctx.setting("ha_dr", "binlog", "sync_binlog")
    if log_bin and log_bin.upper() == "ON" and sync_binlog not in (None, "1"):
        ctx.add("ha_dr", "Medium", "Binary log is not synced on every commit", f"sync_binlog is {sync_binlog}; a crash can lose committed transactions from the binlog and desynchronise replicas.",
                "Set sync_binlog to 1 (the default on MySQL 8) unless a measured write throughput need justifies otherwise.", "Small", ["ha_dr.binlog"])
    flush = ctx.setting("ha_dr", "binlog", "innodb_flush_log_at_trx_commit")
    if flush not in (None, "1"):
        ctx.add("ha_dr", "Medium", "InnoDB does not flush the redo log on every commit", f"innodb_flush_log_at_trx_commit is {flush}; up to a second of committed transactions can be lost on a power failure.",
                "Set it to 1 for the primary; keep 2 only on replicas that can be rebuilt.", "Small", ["ha_dr.binlog"])
    if log_bin and log_bin.upper() == "ON":
        days = ctx.setting("ha_dr", "binlog", "expire_logs_days")
        secs = ctx.setting("ha_dr", "binlog", "binlog_expire_logs_seconds")
        if (days in (None, "0")) and (secs in (None, "0")):
            ctx.add("backup", "Medium", "Binary logs are never purged automatically", "No binlog expiry is set, so the binlog directory grows until the disk fills.",
                    "Set binlog_expire_logs_seconds (or expire_logs_days on older releases) to cover the gap between full backups plus a margin.", "Small", ["ha_dr.binlog"])
    ctx.unknown("backup", "Backup schedule, retention and the date of the last successful restore test",
                "Ask the operations owner for the backup job (mysqldump, mariabackup, xtrabackup or snapshots), retention and restore test log; the server cannot report these", ["backup.backup_tooling_note"])
    # change management
    mig = ctx.require("change_management", "migration_tables", "Schema migration tool in use", "Grant SELECT on information_schema.tables or ask the application team")
    if mig is not None and len(mig) == 0:
        ctx.add("change_management", "Medium", "No schema migration history table found", "No migration tool history table exists, so schema changes are probably applied by hand.",
                "Adopt one migration tool and put every DDL change in version control with a review step; baseline the current schema first.", "Medium", ["change_management.migration_tables"])
    # security
    have_ssl = ctx.setting("security", "ssl", "have_ssl")
    if have_ssl and have_ssl.upper() != "YES":
        ctx.add("security", "High", "TLS is not available on the server", f"have_ssl is {have_ssl}, so every network client sends credentials and data in clear text.",
                "Install a certificate (ssl_ca, ssl_cert, ssl_key), restart, then set require_secure_transport ON once clients are verified.", "Small", ["security.ssl"])
    elif have_ssl and have_ssl.upper() == "YES" and (ctx.setting("security", "ssl", "require_secure_transport") or "OFF").upper() == "OFF":
        ctx.add("security", "Medium", "TLS is available but not required", "require_secure_transport is OFF, so clients may still connect in clear text.",
                "Enable require_secure_transport after confirming every client supports TLS.", "Small", ["security.ssl"])
    if (ctx.setting("security", "local_infile", "local_infile") or "").upper() == "ON":
        ctx.add("security", "Medium", "local_infile is enabled", "A compromised or malicious server can read files from a connecting client's file system through LOAD DATA LOCAL.",
                "Set local_infile OFF unless a specific loader needs it, and then limit it to that user.", "Small", ["security.local_infile"])
    if (ctx.setting("security", "local_infile", "skip_name_resolve") or "").upper() == "OFF":
        ctx.add("security", "Low", "Host name resolution is on for connections", "skip_name_resolve is OFF; DNS delays slow connections and grants keyed on host names depend on DNS being trustworthy.",
                "Turn skip_name_resolve ON and convert host based grants to IP ranges.", "Small", ["security.local_infile"])
    # access
    users = ctx.require("access", "users", "Account list from mysql.user", "Grant SELECT ON mysql.user to the discovery user and rerun")
    if users:
        anon = [u for u in users if (u.get("user") or "") == ""]
        if anon:
            ctx.add("access", "High", "Anonymous accounts exist", f"{len(anon)} account(s) with an empty user name allow logins without identity.", "DROP USER ''@'host' for each.", "Small", ["access.users"])
        empty = [f"{u['user']}@{u['host']}" for u in users if u.get("empty_password") and u.get("account_locked") != "Y" and u.get("password_expired") != "Y"]
        if empty:
            ctx.add("access", "High", "Accounts with an empty password", ", ".join(empty[:8]), "Set a password or convert the account to socket authentication; lock accounts that are not used.", "Small", ["access.users"])
        root_wide = [f"{u['user']}@{u['host']}" for u in users if u.get("user") == "root" and u.get("host") in ("%", "")]
        if root_wide:
            ctx.add("access", "High", "root can log in from any host", ", ".join(root_wide), "Restrict root to localhost and create named administrator accounts for people.", "Small", ["access.users"])
        wild = [f"{u['user']}@{u['host']}" for u in users if u.get("host") == "%" and u.get("user") not in ("root",)]
        if wild:
            ctx.add("access", "Medium", "Accounts accept connections from any host", ", ".join(wild[:8]), "Limit each account's host to the application subnet; the firewall should not be the only control.", "Small", ["access.users"])
    priv = ctx.rows("access", "global_privileges")
    if priv:
        allp = [p["grantee"] for p in priv if "SUPER" in (p.get("privileges") or "") or "ALL PRIVILEGES" in (p.get("privileges") or "")]
        system = ("root", "mysql", "mariadb.sys", "mysql.sys", "mysql.session", "mysql.infoschema", "debian-sys-maint")
        allp = [g for g in allp if g.split("@")[0].strip("'") not in system]
        if allp:
            ctx.add("access", "Medium", "Application or personal accounts hold SUPER", ", ".join(allp[:8]), "Replace SUPER with the specific dynamic privileges each account needs.", "Medium", ["access.global_privileges"])
    life = ctx.setting("access", "password_lifetime", "default_password_lifetime")
    if life == "0":
        ctx.add("access", "Low", "Passwords never expire by default", "default_password_lifetime is 0.", "Set a lifetime for human accounts and exempt service accounts explicitly (ALTER USER ... PASSWORD EXPIRE NEVER).", "Small", ["access.password_lifetime"])
    # cost and capacity
    bp = ctx.rows("cost", "buffer_pool_vs_data")
    if bp and bp[0].get("innodb_data_bytes") and bp[0].get("buffer_pool_bytes"):
        data, pool = float(bp[0]["innodb_data_bytes"]), float(bp[0]["buffer_pool_bytes"])
        if data > pool * 1.5 and data > 4 * 1024 ** 3:
            ctx.add("cost", "Medium", "InnoDB data is much larger than the buffer pool", f"InnoDB data is {data / 1024 ** 3:.1f} GB against a buffer pool of {pool / 1024 ** 3:.1f} GB.",
                    "Raise innodb_buffer_pool_size toward the working set (up to 70 percent of RAM on a dedicated host) and measure Innodb_buffer_pool_reads afterwards.", "Small", ["cost.buffer_pool_vs_data"])
    frag = ctx.rows("cost", "fragmentation")
    if frag:
        ctx.add("cost", "Low", f"{len(frag)} table(s) hold more than 50 MB of free space", ", ".join(f"{r['table_schema']}.{r['table_name']}" for r in frag[:6]),
                "OPTIMIZE TABLE (or `pt-online-schema-change` on busy tables) to reclaim space when it matters for disk or backup size.", "Small", ["cost.fragmentation"])
    cvm = ctx.rows("cost", "connections_vs_max")
    if cvm:
        cur, mx = cvm[0].get("current_connections") or 0, cvm[0].get("max_connections") or 1
        if cur / mx > 0.8:
            ctx.add("cost", "High", "Connection count is near max_connections", f"{cur} of {mx} connections in use.", "Add a proxy or application side pool before raising max_connections.", "Medium", ["cost.connections_vs_max"])
    st = ctx.rows("cost", "status_counters")
    if st:
        vals = {r.get("Variable_name"): r.get("Value") for r in st}
        if vals.get("Innodb_buffer_pool_wait_free") not in (None, "0"):
            ctx.add("cost", "Medium", "InnoDB waited for free pages in the buffer pool", f"Innodb_buffer_pool_wait_free is {vals['Innodb_buffer_pool_wait_free']}, a sign the pool is too small for the write rate.",
                    "Increase innodb_buffer_pool_size and check innodb_io_capacity.", "Small", ["cost.status_counters"])
    # monitoring
    if (ctx.setting("monitoring", "settings", "slow_query_log") or "").upper() == "OFF":
        ctx.add("monitoring", "Medium", "Slow query log is off", "No record of slow statements exists, so performance work has no evidence to start from.",
                "Set slow_query_log ON with long_query_time around 1 second and review with `pt-query-digest` or the Performance Schema.", "Small", ["monitoring.settings"])
    if (ctx.setting("monitoring", "settings", "performance_schema") or "").upper() == "OFF":
        ctx.add("monitoring", "Low", "Performance Schema is off", "Per statement and wait event instrumentation is unavailable.", "Enable performance_schema (restart) with the default instruments.", "Small", ["monitoring.settings"])
    # operations
    myisam = ctx.rows("operations", "myisam_tables")
    if myisam:
        ctx.add("operations", "Medium", f"{len(myisam)} MyISAM table(s) in application schemas", "MyISAM has no crash recovery, no transactions and table level locks: " + ", ".join(f"{r['table_schema']}.{r['table_name']}" for r in myisam[:6]) + ".",
                "Convert to InnoDB (ALTER TABLE ... ENGINE=InnoDB) after checking for FULLTEXT or spatial features that need attention.", "Medium", ["operations.myisam_tables"])
    nopk = ctx.rows("operations", "tables_without_pk")
    if nopk:
        row_repl = (log_bin or "").upper() == "ON" and (ctx.setting("ha_dr", "binlog", "binlog_format") or "").upper() == "ROW"
        ctx.add("operations", "Medium" if row_repl else "Low", f"{len(nopk)} table(s) have no primary key", "InnoDB creates a hidden key and row based replication must scan the whole table to apply each change: " + ", ".join(f"{r['table_schema']}.{r['table_name']}" for r in nopk[:6]) + ".",
                "Add an explicit primary key to each table, starting with the largest.", "Small", ["operations.tables_without_pk"])
    lr = ctx.rows("operations", "long_running")
    if lr:
        ctx.add("operations", "Low", f"{len(lr)} statement(s) running longer than five minutes at collection time", "; ".join(f"id {r['id']} ({r['user']}) {r['time']} s" for r in lr[:4]),
                "Identify whether these are expected jobs; set max_execution_time for application users.", "Small", ["operations.long_running"])
    return ctx


def assess(engine: str, ev: dict, today: date | None = None):
    if engine == "postgres":
        return assess_postgres(ev, today)
    if engine == "mysql":
        return assess_mysql(ev, today)
    raise ValueError("engine must be postgres or mysql")
