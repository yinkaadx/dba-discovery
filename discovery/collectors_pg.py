"""PostgreSQL collectors. Each returns plain rows so evidence is reproducible with psql.
Runs with a read only role; checks that need superuser degrade to an 'unknown' marker instead of failing."""
from __future__ import annotations

import psycopg

AREAS = ["inventory", "architecture", "ha_dr", "change_management", "security", "access", "backup", "cost", "monitoring", "operations"]


def q(conn, sql, params=None):
    try:
        with conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            cols = [d.name for d in cur.description] if cur.description else []
            return {"ok": True, "sql": sql.strip(), "rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    except Exception as e:  # permission or version differences become evidence, not crashes
        conn.rollback()
        return {"ok": False, "sql": sql.strip(), "error": str(e).strip()[:300], "rows": []}


def settings(conn, names):
    return q(conn, "SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name", (names,))


def collect(dsn: str) -> dict:
    ev: dict = {a: {} for a in AREAS}
    with psycopg.connect(dsn, autocommit=True) as conn:
        i = ev["inventory"]
        i["version"] = q(conn, "SELECT version() AS version, current_setting('server_version') AS server_version, pg_postmaster_start_time() AS started_at, now() - pg_postmaster_start_time() AS uptime")
        i["databases"] = q(conn, "SELECT datname, pg_database_size(datname) AS size_bytes, pg_size_pretty(pg_database_size(datname)) AS size, datallowconn, datconnlimit, age(datfrozenxid) AS xid_age FROM pg_database WHERE NOT datistemplate ORDER BY size_bytes DESC")
        i["extensions"] = q(conn, "SELECT extname, extversion FROM pg_extension ORDER BY extname")
        i["core_settings"] = settings(conn, ["data_directory", "listen_addresses", "port", "max_connections", "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size", "timezone", "server_encoding"])
        a = ev["architecture"]
        a["role"] = q(conn, "SELECT pg_is_in_recovery() AS in_recovery")
        a["connections"] = q(conn, "SELECT datname, usename, application_name, state, count(*) AS n FROM pg_stat_activity WHERE datname IS NOT NULL GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 50")
        a["largest_tables"] = q(conn, "SELECT n.nspname AS schema, c.relname AS table, pg_total_relation_size(c.oid) AS total_bytes, pg_size_pretty(pg_total_relation_size(c.oid)) AS total, c.reltuples::bigint AS est_rows FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY total_bytes DESC LIMIT 25")
        a["logical_replication"] = q(conn, "SELECT (SELECT count(*) FROM pg_publication) AS publications, (SELECT count(*) FROM pg_subscription) AS subscriptions")
        a["foreign_servers"] = q(conn, "SELECT srvname, fdwname FROM pg_foreign_server s JOIN pg_foreign_data_wrapper w ON w.oid = s.srvfdw")
        h = ev["ha_dr"]
        h["replication"] = q(conn, "SELECT client_addr, application_name, state, sync_state, write_lag, flush_lag, replay_lag FROM pg_stat_replication")
        h["settings"] = settings(conn, ["wal_level", "archive_mode", "archive_command", "archive_timeout", "max_wal_senders", "wal_keep_size", "synchronous_standby_names", "synchronous_commit", "hot_standby", "primary_conninfo", "restore_command"])
        h["archiver"] = q(conn, "SELECT archived_count, last_archived_wal, last_archived_time, failed_count, last_failed_wal, last_failed_time FROM pg_stat_archiver")
        h["slots"] = q(conn, "SELECT slot_name, slot_type, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal FROM pg_replication_slots")
        cm = ev["change_management"]
        cm["migration_tables"] = q(conn, "SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('flyway_schema_history','schema_migrations','alembic_version','django_migrations','databasechangelog','knex_migrations','__EFMigrationsHistory','prisma_migrations','_prisma_migrations','goose_db_version') ORDER BY 1,2")
        cm["ddl_logging"] = settings(conn, ["log_statement", "log_min_duration_statement", "log_line_prefix"])
        cm["event_triggers"] = q(conn, "SELECT evtname, evtevent, evtenabled FROM pg_event_trigger")
        s = ev["security"]
        s["ssl"] = settings(conn, ["ssl", "ssl_cert_file", "ssl_key_file", "ssl_min_protocol_version", "password_encryption", "listen_addresses"])
        s["hba"] = q(conn, "SELECT line_number, type, database, user_name, address, auth_method FROM pg_hba_file_rules ORDER BY line_number")
        s["ssl_connections"] = q(conn, "SELECT ssl, count(*) AS n FROM pg_stat_ssl s JOIN pg_stat_activity a USING (pid) WHERE a.datname IS NOT NULL GROUP BY ssl")
        ac = ev["access"]
        ac["roles"] = q(conn, "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, rolbypassrls, rolreplication, rolconnlimit, rolvaliduntil FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%' ORDER BY rolsuper DESC, rolname")
        ac["public_schema"] = q(conn, "SELECT nspname, nspacl FROM pg_namespace WHERE nspname = 'public'")
        ac["db_acl"] = q(conn, "SELECT datname, datacl FROM pg_database WHERE NOT datistemplate")
        b = ev["backup"]
        b["settings"] = settings(conn, ["archive_mode", "archive_command", "wal_level", "checkpoint_timeout", "max_wal_size", "full_page_writes"])
        b["archiver"] = h["archiver"]
        b["backup_tooling_note"] = {"ok": True, "sql": "", "rows": [{"note": "Backup jobs, retention and restore tests live outside the database; request the backup schedule, retention policy and the last restore test record"}]}
        c = ev["cost"]
        c["cache_hit"] = q(conn, "SELECT datname, blks_hit, blks_read, CASE WHEN blks_hit + blks_read = 0 THEN NULL ELSE round(100.0 * blks_hit / (blks_hit + blks_read), 2) END AS cache_hit_pct, temp_files, pg_size_pretty(temp_bytes) AS temp_bytes, deadlocks, stats_reset FROM pg_stat_database WHERE datname NOT LIKE 'template%' ORDER BY blks_read DESC")
        c["unused_indexes"] = q(conn, "SELECT s.schemaname, s.relname AS table, s.indexrelname AS index, s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid = s.indexrelid WHERE s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 25")
        c["dead_tuples"] = q(conn, "SELECT schemaname, relname, n_live_tup, n_dead_tup, CASE WHEN n_live_tup = 0 THEN NULL ELSE round(100.0 * n_dead_tup / n_live_tup, 1) END AS dead_pct, last_autovacuum, last_autoanalyze FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 25")
        c["connections_vs_max"] = q(conn, "SELECT (SELECT count(*) FROM pg_stat_activity) AS current_connections, current_setting('max_connections')::int AS max_connections")
        m = ev["monitoring"]
        m["settings"] = settings(conn, ["track_io_timing", "track_activities", "track_counts", "log_min_duration_statement", "log_checkpoints", "log_lock_waits", "log_autovacuum_min_duration", "autovacuum", "shared_preload_libraries", "log_destination", "logging_collector"])
        m["pg_stat_statements"] = q(conn, "SELECT count(*) AS installed FROM pg_extension WHERE extname = 'pg_stat_statements'")
        o = ev["operations"]
        o["long_running"] = q(conn, "SELECT pid, datname, usename, state, now() - query_start AS running_for, left(query, 120) AS query FROM pg_stat_activity WHERE state <> 'idle' AND now() - query_start > interval '5 minutes' ORDER BY query_start LIMIT 20")
        o["lock_waits"] = q(conn, "SELECT count(*) AS waiting FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
        o["wraparound"] = q(conn, "SELECT datname, age(datfrozenxid) AS xid_age, current_setting('autovacuum_freeze_max_age')::bigint AS freeze_max_age, round(100.0 * age(datfrozenxid) / current_setting('autovacuum_freeze_max_age')::bigint, 1) AS pct_of_limit FROM pg_database WHERE NOT datistemplate ORDER BY xid_age DESC")
        o["invalid_indexes"] = q(conn, "SELECT n.nspname, c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE NOT i.indisvalid")
        o["tables_without_pk"] = q(conn, "SELECT n.nspname AS schema, c.relname AS table FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') ORDER BY 1,2 LIMIT 50")
    return ev
