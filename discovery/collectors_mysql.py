"""MySQL and MariaDB collectors, read only, tolerant of version differences."""
from __future__ import annotations

import pymysql

from .collectors_pg import AREAS


def q(conn, sql, params=None):
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return {"ok": True, "sql": sql.strip(), "rows": [dict(r) for r in cur.fetchall()]}
    except Exception as e:
        return {"ok": False, "sql": sql.strip(), "error": str(e).strip()[:300], "rows": []}


def variables(conn, names):
    rows = q(conn, "SHOW GLOBAL VARIABLES")
    if not rows["ok"]:
        return rows
    wanted = {n.lower() for n in names}
    return {"ok": True, "sql": "SHOW GLOBAL VARIABLES (filtered)", "rows": [r for r in rows["rows"] if r.get("Variable_name", "").lower() in wanted]}


def collect(dsn: dict) -> dict:
    ev: dict = {a: {} for a in AREAS}
    conn = pymysql.connect(host=dsn["host"], port=int(dsn.get("port", 3306)), user=dsn["user"], password=dsn["password"], database=dsn.get("database"), connect_timeout=10, read_timeout=30)
    try:
        i = ev["inventory"]
        i["version"] = q(conn, "SELECT VERSION() AS version, @@version_comment AS flavour, @@hostname AS host, @@port AS port")
        i["uptime"] = q(conn, "SHOW GLOBAL STATUS LIKE 'Uptime'")
        i["databases"] = q(conn, "SELECT table_schema AS db, ROUND(SUM(data_length + index_length)) AS size_bytes, COUNT(*) AS tables FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY table_schema ORDER BY size_bytes DESC")
        i["engines"] = q(conn, "SELECT engine, COUNT(*) AS tables FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY engine")
        i["core_settings"] = variables(conn, ["datadir", "max_connections", "innodb_buffer_pool_size", "innodb_file_per_table", "character_set_server", "collation_server", "sql_mode", "time_zone"])
        a = ev["architecture"]
        a["connections"] = q(conn, "SELECT user, host, db, command, COUNT(*) AS n FROM information_schema.processlist GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 50")
        a["largest_tables"] = q(conn, "SELECT table_schema, table_name, engine, table_rows, data_length + index_length AS total_bytes, data_free FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY total_bytes DESC LIMIT 25")
        a["server_id"] = variables(conn, ["server_id", "read_only", "super_read_only"])
        h = ev["ha_dr"]
        h["binlog"] = variables(conn, ["log_bin", "binlog_format", "expire_logs_days", "binlog_expire_logs_seconds", "sync_binlog", "gtid_mode", "gtid_strict_mode", "log_slave_updates", "innodb_flush_log_at_trx_commit"])
        rep = q(conn, "SHOW REPLICA STATUS")
        if not rep["ok"]:
            rep = q(conn, "SHOW SLAVE STATUS")
        h["replica_status"] = rep
        h["replicas_connected"] = q(conn, "SELECT COUNT(*) AS replicas FROM information_schema.processlist WHERE command IN ('Binlog Dump','Binlog Dump GTID')")
        cm = ev["change_management"]
        cm["migration_tables"] = q(conn, "SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('flyway_schema_history','schema_migrations','alembic_version','django_migrations','databasechangelog','knex_migrations','__EFMigrationsHistory','_prisma_migrations','goose_db_version','phinxlog')")
        cm["ddl_logging"] = variables(conn, ["general_log", "log_output"])
        s = ev["security"]
        s["ssl"] = variables(conn, ["have_ssl", "ssl_cert", "ssl_key", "ssl_ca", "require_secure_transport", "tls_version"])
        s["auth_plugins"] = variables(conn, ["default_authentication_plugin", "authentication_policy", "validate_password.policy", "simple_password_check"])
        s["local_infile"] = variables(conn, ["local_infile", "secure_file_priv", "skip_name_resolve"])
        ac = ev["access"]
        # MariaDB 10.4+: the truth is the JSON in mysql.global_priv (locked flag, real plugin); mysql.user is only a compatibility view there
        users = q(conn, "SELECT User AS user, Host AS host, CASE WHEN JSON_EXTRACT(Priv, '$.auth_or[*].plugin') LIKE '%unix_socket%' THEN 'unix_socket' ELSE COALESCE(JSON_VALUE(Priv, '$.plugin'), 'mysql_native_password') END AS plugin, IF(JSON_EXTRACT(Priv, '$.account_locked') = true, 'Y', 'N') AS account_locked, IF(COALESCE(JSON_VALUE(Priv, '$.authentication_string'), '') = '' AND JSON_EXTRACT(Priv, '$.auth_or') IS NULL AND COALESCE(JSON_VALUE(Priv, '$.plugin'), 'mysql_native_password') NOT IN ('unix_socket','auth_socket'), 1, 0) AS empty_password, FROM_UNIXTIME(JSON_VALUE(Priv, '$.password_last_changed')) AS password_last_changed FROM mysql.global_priv ORDER BY User, Host")
        if not users["ok"]:  # MySQL 5.7 and 8
            users = q(conn, "SELECT user AS user, host AS host, plugin AS plugin, password_expired AS password_expired, account_locked AS account_locked, IF(authentication_string = '' AND plugin NOT IN ('unix_socket','auth_socket'), 1, 0) AS empty_password, password_last_changed FROM mysql.user ORDER BY user, host")
        if not users["ok"]:  # older releases keep the hash in Password and have no lock flag
            users = q(conn, "SELECT user AS user, host AS host, plugin AS plugin, password_expired AS password_expired, IF(COALESCE(authentication_string, '') = '' AND COALESCE(password, '') = '' AND plugin NOT IN ('unix_socket','auth_socket'), 1, 0) AS empty_password FROM mysql.user ORDER BY user, host")
        ac["users"] = users
        ac["global_privileges"] = q(conn, "SELECT grantee, GROUP_CONCAT(privilege_type ORDER BY privilege_type) AS privileges, MAX(is_grantable) AS grantable FROM information_schema.user_privileges GROUP BY grantee")
        ac["password_lifetime"] = variables(conn, ["default_password_lifetime", "disconnect_on_expired_password"])
        b = ev["backup"]
        b["binlog_retention"] = h["binlog"]
        b["backup_tooling_note"] = {"ok": True, "sql": "", "rows": [{"note": "Backups (mysqldump, mariabackup, xtrabackup, cloud snapshots), retention and restore tests live outside the server; request the schedule, retention policy and the last restore test record"}]}
        c = ev["cost"]
        c["buffer_pool_vs_data"] = q(conn, "SELECT @@innodb_buffer_pool_size AS buffer_pool_bytes, (SELECT SUM(data_length + index_length) FROM information_schema.tables WHERE engine = 'InnoDB') AS innodb_data_bytes")
        c["fragmentation"] = q(conn, "SELECT table_schema, table_name, data_free, data_length + index_length AS total_bytes FROM information_schema.tables WHERE data_free > 50*1024*1024 AND table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY data_free DESC LIMIT 25")
        c["connections_vs_max"] = q(conn, "SELECT (SELECT COUNT(*) FROM information_schema.processlist) AS current_connections, @@max_connections AS max_connections")
        c["status_counters"] = q(conn, "SHOW GLOBAL STATUS WHERE Variable_name IN ('Max_used_connections','Aborted_connects','Created_tmp_disk_tables','Innodb_buffer_pool_wait_free','Slow_queries','Threads_connected')")
        m = ev["monitoring"]
        m["settings"] = variables(conn, ["slow_query_log", "long_query_time", "log_queries_not_using_indexes", "performance_schema", "log_error", "log_warnings", "innodb_monitor_enable"])
        o = ev["operations"]
        o["long_running"] = q(conn, "SELECT id, user, host, db, command, time, state, LEFT(info, 120) AS query FROM information_schema.processlist WHERE command NOT IN ('Sleep','Binlog Dump','Binlog Dump GTID') AND time > 300 ORDER BY time DESC LIMIT 20")
        lw = q(conn, "SELECT COUNT(*) AS waiting FROM information_schema.innodb_lock_waits")
        if not lw["ok"]:
            lw = q(conn, "SELECT COUNT(*) AS waiting FROM performance_schema.data_lock_waits")
        o["lock_waits"] = lw
        # information_schema.statistics is visible with global SELECT on every engine; table_constraints is filtered on MariaDB
        o["tables_without_pk"] = q(conn, "SELECT t.table_schema, t.table_name, t.engine FROM information_schema.tables t WHERE t.table_type = 'BASE TABLE' AND t.table_schema NOT IN ('mysql','information_schema','performance_schema','sys') AND NOT EXISTS (SELECT 1 FROM information_schema.statistics s WHERE s.table_schema = t.table_schema AND s.table_name = t.table_name AND s.index_name = 'PRIMARY') ORDER BY 1,2 LIMIT 50")
        o["myisam_tables"] = q(conn, "SELECT table_schema, table_name FROM information_schema.tables WHERE engine = 'MyISAM' AND table_schema NOT IN ('mysql','information_schema','performance_schema','sys') LIMIT 50")
    finally:
        conn.close()
    return ev
