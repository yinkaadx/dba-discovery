"""Rule checks on synthetic evidence: each rule fires on the condition it describes and stays quiet otherwise."""
from __future__ import annotations

import copy
from datetime import date

import pytest

from discovery.collectors_pg import AREAS
from discovery.rules import assess_mysql, assess_postgres

TODAY = date(2026, 9, 6)


def ok(rows, sql="SELECT 1"):
    return {"ok": True, "sql": sql, "rows": rows}


def fail(msg="permission denied"):
    return {"ok": False, "sql": "SELECT 1", "error": msg, "rows": []}


def pg_settings(**kv):
    return ok([{"name": k, "setting": v, "unit": None, "source": "configuration file"} for k, v in kv.items()])


def my_vars(**kv):
    return ok([{"Variable_name": k, "Value": v} for k, v in kv.items()])


def healthy_pg():
    ev = {a: {} for a in AREAS}
    ev["inventory"]["version"] = ok([{"version": "PostgreSQL 16.4", "server_version": "16.4", "started_at": "2026-01-01", "uptime": "10 days"}])
    ev["architecture"]["role"] = ok([{"in_recovery": False}])
    ev["ha_dr"]["replication"] = ok([{"client_addr": "10.0.0.5", "application_name": "standby1", "state": "streaming", "sync_state": "sync"}])
    ev["ha_dr"]["settings"] = pg_settings(wal_level="replica", synchronous_standby_names="standby1")
    ev["ha_dr"]["slots"] = ok([{"slot_name": "standby1", "slot_type": "physical", "active": True, "retained_wal": "16 MB"}])
    ev["backup"]["settings"] = pg_settings(archive_mode="on", archive_command="pgbackrest archive-push %p")
    ev["backup"]["archiver"] = ok([{"archived_count": 100, "last_archived_wal": "0001", "last_archived_time": "2026-09-06 10:00", "failed_count": 0, "last_failed_wal": None, "last_failed_time": None}])
    ev["change_management"]["migration_tables"] = ok([{"table_schema": "public", "table_name": "flyway_schema_history"}])
    ev["change_management"]["ddl_logging"] = pg_settings(log_statement="ddl")
    ev["change_management"]["event_triggers"] = ok([])
    ev["security"]["ssl"] = pg_settings(ssl="on", password_encryption="scram-sha-256", listen_addresses="*")
    ev["security"]["hba"] = ok([{"line_number": 1, "type": "hostssl", "database": ["all"], "user_name": ["all"], "address": ["10.0.0.0/8"], "auth_method": "scram-sha-256"}])
    ev["security"]["ssl_connections"] = ok([{"ssl": True, "n": 5}])
    ev["access"]["roles"] = ok([{"rolname": "postgres", "rolsuper": True, "rolcanlogin": True, "rolvaliduntil": None, "rolbypassrls": False},
                                {"rolname": "app", "rolsuper": False, "rolcanlogin": True, "rolvaliduntil": "2027-01-01", "rolbypassrls": False}])
    ev["access"]["public_schema"] = ok([{"nspname": "public", "nspacl": "{postgres=UC/postgres,=U/postgres}"}])
    ev["cost"]["cache_hit"] = ok([{"datname": "app", "blks_hit": 1000000, "blks_read": 1000, "cache_hit_pct": 99.9, "deadlocks": 0, "stats_reset": "2026-01-01"}])
    ev["cost"]["unused_indexes"] = ok([])
    ev["cost"]["dead_tuples"] = ok([{"relname": "orders", "n_live_tup": 100000, "n_dead_tup": 100, "dead_pct": 0.1}])
    ev["cost"]["connections_vs_max"] = ok([{"current_connections": 20, "max_connections": 200}])
    ev["monitoring"]["settings"] = pg_settings(log_min_duration_statement="1000", autovacuum="on", track_io_timing="on", log_checkpoints="on", log_lock_waits="on", logging_collector="on", log_destination="stderr")
    ev["monitoring"]["pg_stat_statements"] = ok([{"installed": 1}])
    ev["operations"]["wraparound"] = ok([{"datname": "app", "xid_age": 1000000, "freeze_max_age": 200000000, "pct_of_limit": 0.5}])
    ev["operations"]["invalid_indexes"] = ok([])
    ev["operations"]["tables_without_pk"] = ok([])
    ev["operations"]["long_running"] = ok([])
    return ev


def ids(ctx):
    return {f.title for f in ctx.findings}


def test_healthy_postgres_raises_nothing():
    ctx = assess_postgres(healthy_pg(), TODAY)
    assert ctx.findings == []
    assert [u.area for u in ctx.unknowns] == ["backup"]  # backup schedule always needs a human


def test_postgres_single_instance_without_archiving():
    ev = healthy_pg()
    ev["ha_dr"]["replication"] = ok([])
    ev["backup"]["settings"] = pg_settings(archive_mode="off")
    ev["ha_dr"]["settings"] = pg_settings(wal_level="minimal")
    ctx = assess_postgres(ev, TODAY)
    titles = ids(ctx)
    assert "Single primary with no streaming replica" in titles
    assert "WAL archiving is off" in titles
    assert "wal_level is minimal" in titles
    assert all(f.severity == "High" for f in ctx.findings if f.title in ("WAL archiving is off", "wal_level is minimal", "Single primary with no streaming replica"))


def test_postgres_standby_is_not_reported_as_single_primary():
    ev = healthy_pg()
    ev["architecture"]["role"] = ok([{"in_recovery": True}])
    ev["ha_dr"]["replication"] = ok([])
    assert "Single primary with no streaming replica" not in ids(assess_postgres(ev, TODAY))


def test_postgres_end_of_life_version():
    ev = healthy_pg()
    ev["inventory"]["version"][
        "rows"] = [{"version": "PostgreSQL 12.18", "server_version": "12.18", "started_at": "x", "uptime": "y"}]
    ctx = assess_postgres(ev, TODAY)
    f = [f for f in ctx.findings if "end of support" in f.title][0]
    assert f.severity == "High" and f.effort == "Large" and f.id == "PG-INV-001"
    ev["inventory"]["version"]["rows"][0]["server_version"] = "14.12"
    f = [f for f in assess_postgres(ev, TODAY).findings if "end of support" in f.title][0]
    assert f.severity == "Medium"  # PostgreSQL 14 ends in November 2026


def test_postgres_security_rules():
    ev = healthy_pg()
    ev["security"]["ssl"] = pg_settings(ssl="off", password_encryption="md5", listen_addresses="*")
    ev["security"]["hba"] = ok([{"line_number": 3, "type": "host", "database": ["all"], "user_name": ["all"], "address": ["0.0.0.0/0"], "auth_method": "trust"},
                                {"line_number": 4, "type": "host", "database": ["all"], "user_name": ["all"], "address": ["10.0.0.0/8"], "auth_method": "md5"}])
    titles = ids(assess_postgres(ev, TODAY))
    assert "TLS is off for network connections" in titles
    assert "Passwords are hashed with md5" in titles
    assert "Network clients can connect without a password" in titles
    assert "Authentication rules accept any source address" in titles


def test_postgres_missing_permission_becomes_unknown_not_finding():
    ev = healthy_pg()
    ev["security"]["hba"] = fail("permission denied for function pg_hba_file_rules")
    ctx = assess_postgres(ev, TODAY)
    assert not any("pg_hba" in f.title for f in ctx.findings)
    u = [u for u in ctx.unknowns if u.area == "security"][0]
    assert "pg_hba_file_rules" in u.how_to_obtain and u.evidence == ["security.hba"]


def test_postgres_access_and_capacity_rules():
    ev = healthy_pg()
    ev["access"]["roles"]["rows"].append({"rolname": "deploy", "rolsuper": True, "rolcanlogin": True, "rolvaliduntil": None, "rolbypassrls": False})
    ev["access"]["public_schema"] = ok([{"nspname": "public", "nspacl": "{postgres=UC/postgres,=UC/postgres}"}])
    ev["cost"]["cache_hit"]["rows"][0].update({"blks_read": 5000000, "cache_hit_pct": 80.0, "deadlocks": 3})
    ev["cost"]["connections_vs_max"] = ok([{"current_connections": 190, "max_connections": 200}])
    ev["cost"]["dead_tuples"] = ok([{"relname": "events", "n_live_tup": 100000, "n_dead_tup": 40000, "dead_pct": 40.0}])
    ev["operations"]["wraparound"] = ok([{"datname": "app", "xid_age": 170000000, "freeze_max_age": 200000000, "pct_of_limit": 85.0}])
    ctx = assess_postgres(ev, TODAY)
    titles = ids(ctx)
    assert "Additional superuser roles exist" in titles
    assert "Any role can create objects in the public schema" in titles
    assert "Low buffer cache hit ratio in app" in titles
    assert "Deadlocks recorded in app" in titles
    assert "Connection count is near max_connections" in titles
    assert "Tables carry a high share of dead rows" in titles
    assert any(f.severity == "High" and "freeze limit" in f.title for f in ctx.findings)


def test_finding_ids_are_unique_and_sequential_per_area():
    ev = healthy_pg()
    ev["monitoring"]["settings"] = pg_settings(log_min_duration_statement="-1", autovacuum="off", track_io_timing="off", log_checkpoints="off", log_lock_waits="off", logging_collector="off", log_destination="stderr")
    ev["monitoring"]["pg_stat_statements"] = ok([{"installed": 0}])
    ctx = assess_postgres(ev, TODAY)
    mon = [f.id for f in ctx.findings if f.area == "monitoring"]
    assert mon == [f"PG-MON-{n:03d}" for n in range(1, len(mon) + 1)]
    assert len(set(f.id for f in ctx.findings)) == len(ctx.findings)
    assert any(f.title == "autovacuum is off" and f.severity == "High" for f in ctx.findings)


# ---------------------------------------------------------------- MySQL
def healthy_mysql():
    ev = {a: {} for a in AREAS}
    ev["inventory"]["version"] = ok([{"version": "8.4.3", "flavour": "MySQL Community Server - GPL", "host": "db1", "port": 3306}])
    ev["ha_dr"]["binlog"] = my_vars(log_bin="ON", binlog_format="ROW", binlog_expire_logs_seconds="604800", sync_binlog="1", innodb_flush_log_at_trx_commit="1")
    ev["ha_dr"]["replica_status"] = ok([])
    ev["ha_dr"]["replicas_connected"] = ok([{"replicas": 1}])
    ev["change_management"]["migration_tables"] = ok([{"table_schema": "app", "table_name": "schema_migrations"}])
    ev["security"]["ssl"] = my_vars(have_ssl="YES", require_secure_transport="ON")
    ev["security"]["local_infile"] = my_vars(local_infile="OFF", skip_name_resolve="ON")
    ev["access"]["users"] = ok([{"user": "root", "host": "localhost", "plugin": "caching_sha2_password", "password_expired": "N", "account_locked": "N", "empty_password": 0},
                                {"user": "app", "host": "10.0.0.%", "plugin": "caching_sha2_password", "password_expired": "N", "account_locked": "N", "empty_password": 0}])
    ev["access"]["global_privileges"] = ok([{"grantee": "'root'@'localhost'", "privileges": "ALL PRIVILEGES", "grantable": "YES"}, {"grantee": "'app'@'10.0.0.%'", "privileges": "USAGE", "grantable": "NO"}])
    ev["access"]["password_lifetime"] = my_vars(default_password_lifetime="180")
    ev["cost"]["buffer_pool_vs_data"] = ok([{"buffer_pool_bytes": 8 * 1024 ** 3, "innodb_data_bytes": 6 * 1024 ** 3}])
    ev["cost"]["fragmentation"] = ok([])
    ev["cost"]["connections_vs_max"] = ok([{"current_connections": 10, "max_connections": 500}])
    ev["cost"]["status_counters"] = ok([{"Variable_name": "Innodb_buffer_pool_wait_free", "Value": "0"}])
    ev["monitoring"]["settings"] = my_vars(slow_query_log="ON", long_query_time="1", performance_schema="ON")
    ev["operations"]["myisam_tables"] = ok([])
    ev["operations"]["tables_without_pk"] = ok([])
    ev["operations"]["long_running"] = ok([])
    return ev


def test_healthy_mysql_raises_nothing():
    ctx = assess_mysql(healthy_mysql(), TODAY)
    assert ctx.findings == [], [f.title for f in ctx.findings]


def test_mysql_end_of_life_lines():
    ev = healthy_mysql()
    ev["inventory"]["version"]["rows"][0]["version"] = "8.0.39"
    assert any("MySQL 8.0 is past end of support" == f.title for f in assess_mysql(ev, TODAY).findings)
    ev["inventory"]["version"]["rows"][0].update({"version": "10.11.8-MariaDB-log", "flavour": "mariadb.org binary distribution"})
    assert not any("end of support" in f.title for f in assess_mysql(ev, TODAY).findings)
    ev["inventory"]["version"]["rows"][0]["version"] = "10.6.18-MariaDB"
    assert any("MariaDB 10.6 is past end of support" == f.title for f in assess_mysql(ev, TODAY).findings)


def test_mysql_durability_and_replication_rules():
    ev = healthy_mysql()
    ev["ha_dr"]["binlog"] = my_vars(log_bin="OFF", innodb_flush_log_at_trx_commit="2")
    ev["ha_dr"]["replicas_connected"] = ok([{"replicas": 0}])
    titles = ids(assess_mysql(ev, TODAY))
    assert {"Binary logging is off", "Single server with no replica", "InnoDB does not flush the redo log on every commit"} <= titles
    ev = healthy_mysql()
    ev["ha_dr"]["binlog"] = my_vars(log_bin="ON", binlog_format="ROW", sync_binlog="0", expire_logs_days="0", binlog_expire_logs_seconds="0", innodb_flush_log_at_trx_commit="1")
    ev["ha_dr"]["replica_status"] = ok([{"Replica_IO_Running": "Yes", "Replica_SQL_Running": "No", "Seconds_Behind_Source": None}])
    ctx = assess_mysql(ev, TODAY)
    titles = ids(ctx)
    assert "Binary log is not synced on every commit" in titles
    assert "Binary logs are never purged automatically" in titles
    assert "Replication threads are not running" in titles
    assert [f.area for f in ctx.findings if f.title == "Binary logs are never purged automatically"] == ["backup"]


def test_mysql_security_and_access_rules():
    ev = healthy_mysql()
    ev["security"]["ssl"] = my_vars(have_ssl="DISABLED")
    ev["security"]["local_infile"] = my_vars(local_infile="ON", skip_name_resolve="OFF")
    ev["access"]["users"]["rows"] += [{"user": "", "host": "localhost", "plugin": "", "password_expired": "N", "account_locked": "N", "empty_password": 1},
                                      {"user": "root", "host": "%", "plugin": "mysql_native_password", "password_expired": "N", "account_locked": "N", "empty_password": 0},
                                      {"user": "legacy", "host": "%", "plugin": "mysql_native_password", "password_expired": "N", "account_locked": "N", "empty_password": 1},
                                      {"user": "mariadb.sys", "host": "localhost", "plugin": "mysql_native_password", "password_expired": "N", "account_locked": "Y", "empty_password": 1}]
    ev["access"]["global_privileges"]["rows"].append({"grantee": "'legacy'@'%'", "privileges": "ALL PRIVILEGES", "grantable": "YES"})
    ev["access"]["password_lifetime"] = my_vars(default_password_lifetime="0")
    ctx = assess_mysql(ev, TODAY)
    titles = ids(ctx)
    assert {"TLS is not available on the server", "local_infile is enabled", "Host name resolution is on for connections", "Anonymous accounts exist",
            "Accounts with an empty password", "root can log in from any host", "Accounts accept connections from any host", "Application or personal accounts hold SUPER",
            "Passwords never expire by default"} <= titles
    empty = [f for f in ctx.findings if f.title == "Accounts with an empty password"][0]
    assert "legacy@%" in empty.detail and "mariadb.sys" not in empty.detail  # locked system account is not reported


def test_mysql_operations_rules_scale_with_replication_format():
    ev = healthy_mysql()
    ev["operations"]["myisam_tables"] = ok([{"table_schema": "shop", "table_name": "legacy_log"}])
    ev["operations"]["tables_without_pk"] = ok([{"table_schema": "shop", "table_name": "events", "engine": "InnoDB"}])
    ctx = assess_mysql(ev, TODAY)
    nopk = [f for f in ctx.findings if "no primary key" in f.title][0]
    assert nopk.severity == "Medium"  # row based binlog is on in the healthy baseline
    ev["ha_dr"]["binlog"] = my_vars(log_bin="OFF")
    nopk = [f for f in assess_mysql(ev, TODAY).findings if "no primary key" in f.title][0]
    assert nopk.severity == "Low"
    assert any(f.title.endswith("MyISAM table(s) in application schemas") for f in ctx.findings)


def test_every_finding_carries_evidence_and_valid_labels():
    ev = healthy_pg()
    for area in ev:
        for key in ev[area]:
            pass
    broken = copy.deepcopy(ev)
    broken["ha_dr"]["replication"] = ok([])
    broken["backup"]["settings"] = pg_settings(archive_mode="off")
    broken["monitoring"]["pg_stat_statements"] = ok([{"installed": 0}])
    for ctx in (assess_postgres(broken, TODAY), assess_mysql(healthy_mysql(), TODAY)):
        for f in ctx.findings:
            assert f.evidence, f.id
            for e in f.evidence:
                area, key = e.split(".")
                assert key in ctx.ev[area], e
            assert f.severity in ("High", "Medium", "Low", "Info") and f.effort in ("Small", "Medium", "Large")
