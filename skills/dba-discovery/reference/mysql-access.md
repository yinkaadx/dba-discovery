# MySQL and MariaDB: read only access and the manual query catalogue

## The discovery user

Ask the owner to run this as root. Global SELECT lets the account read `information_schema`, `performance_schema` and the catalogue; PROCESS shows sessions; the replication monitor privilege allows `SHOW REPLICA STATUS`; SELECT on `mysql.*` reads the account list.

MySQL 8 and 9:

```sql
CREATE USER 'discovery'@'10.0.0.%' IDENTIFIED BY 'choose a long password' PASSWORD EXPIRE INTERVAL 90 DAY;
GRANT SELECT, PROCESS, SHOW DATABASES, REPLICATION CLIENT ON *.* TO 'discovery'@'10.0.0.%';
GRANT SELECT ON mysql.* TO 'discovery'@'10.0.0.%';
```

MariaDB 10.5 and later (privilege names differ):

```sql
CREATE USER 'discovery'@'10.0.0.%' IDENTIFIED BY 'choose a long password';
GRANT SELECT, PROCESS, SHOW DATABASES, BINLOG MONITOR, REPLICA MONITOR ON *.* TO 'discovery'@'10.0.0.%';
GRANT SELECT ON mysql.* TO 'discovery'@'10.0.0.%';
```

Tested on MariaDB 10.11: without REPLICA MONITOR, `ha_dr.replica_status` fails with error 1227 and the single server rule stays silent (an unknown is recorded); with it every block collects. On MariaDB the account list is read from `mysql.global_priv` (JSON) because the `mysql.user` view there hides the lock flag and the socket plugin; on MySQL the collector falls back to `mysql.user`. `information_schema.table_constraints` is privilege filtered on MariaDB, so the primary key check uses `information_schema.statistics`, which is visible with global SELECT.

Managed services (RDS, Aurora, Cloud SQL, Azure) refuse some grants; whatever fails is reported with the server's error text and becomes an unknown with the grant named.

## Connection string

`mysql://discovery:PASSWORD@host:3306/app`. The password never appears in any output file; only the user name does.

## Manual query catalogue

When the collector cannot run, execute these in the `mysql` client as the discovery user and paste the results under the same key in `evidence.json`, then run `python -m discovery assess --run runs/<name>`. This list is generated from `discovery/collectors_mysql.py` by `python tools/render_queries.py`. Three blocks use fallbacks not shown here: `ha_dr.replica_status` (`SHOW REPLICA STATUS`, then `SHOW SLAVE STATUS`), `operations.lock_waits` (`information_schema.innodb_lock_waits`, then `performance_schema.data_lock_waits`) and `access.users` (`mysql.global_priv` on MariaDB, then `mysql.user` with `account_locked`, then the legacy `mysql.user` layout).

<!-- queries:start -->
### `inventory.version`
```sql
SELECT VERSION() AS version, @@version_comment AS flavour, @@hostname AS host, @@port AS port
```

### `inventory.uptime`
```sql
SHOW GLOBAL STATUS LIKE 'Uptime'
```

### `inventory.databases`
```sql
SELECT table_schema AS db, ROUND(SUM(data_length + index_length)) AS size_bytes, COUNT(*) AS tables FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY table_schema ORDER BY size_bytes DESC
```

### `inventory.engines`
```sql
SELECT engine, COUNT(*) AS tables FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY engine
```

### `inventory.core_settings`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('datadir', 'max_connections', 'innodb_buffer_pool_size', 'innodb_file_per_table', 'character_set_server', 'collation_server', 'sql_mode', 'time_zone');
```

### `architecture.connections`
```sql
SELECT user, host, db, command, COUNT(*) AS n FROM information_schema.processlist GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 50
```

### `architecture.largest_tables`
```sql
SELECT table_schema, table_name, engine, table_rows, data_length + index_length AS total_bytes, data_free FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY total_bytes DESC LIMIT 25
```

### `architecture.server_id`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('server_id', 'read_only', 'super_read_only');
```

### `ha_dr.binlog`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('log_bin', 'binlog_format', 'expire_logs_days', 'binlog_expire_logs_seconds', 'sync_binlog', 'gtid_mode', 'gtid_strict_mode', 'log_slave_updates', 'innodb_flush_log_at_trx_commit');
```

### `ha_dr.replica_status`
First attempt (the collector falls back to the alternatives named above the catalogue when this fails):
```sql
SHOW REPLICA STATUS
```

### `ha_dr.replicas_connected`
```sql
SELECT COUNT(*) AS replicas FROM information_schema.processlist WHERE command IN ('Binlog Dump','Binlog Dump GTID')
```

### `change_management.migration_tables`
```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('flyway_schema_history','schema_migrations','alembic_version','django_migrations','databasechangelog','knex_migrations','__EFMigrationsHistory','_prisma_migrations','goose_db_version','phinxlog')
```

### `change_management.ddl_logging`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('general_log', 'log_output');
```

### `security.ssl`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('have_ssl', 'ssl_cert', 'ssl_key', 'ssl_ca', 'require_secure_transport', 'tls_version');
```

### `security.auth_plugins`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('default_authentication_plugin', 'authentication_policy', 'validate_password.policy', 'simple_password_check');
```

### `security.local_infile`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('local_infile', 'secure_file_priv', 'skip_name_resolve');
```

### `access.users`
First attempt (the collector falls back to the alternatives named above the catalogue when this fails):
```sql
SELECT User AS user, Host AS host, CASE WHEN JSON_EXTRACT(Priv, '$.auth_or[*].plugin') LIKE '%unix_socket%' THEN 'unix_socket' ELSE COALESCE(JSON_VALUE(Priv, '$.plugin'), 'mysql_native_password') END AS plugin, IF(JSON_EXTRACT(Priv, '$.account_locked') = true, 'Y', 'N') AS account_locked, IF(COALESCE(JSON_VALUE(Priv, '$.authentication_string'), '') = '' AND JSON_EXTRACT(Priv, '$.auth_or') IS NULL AND COALESCE(JSON_VALUE(Priv, '$.plugin'), 'mysql_native_password') NOT IN ('unix_socket','auth_socket'), 1, 0) AS empty_password, FROM_UNIXTIME(JSON_VALUE(Priv, '$.password_last_changed')) AS password_last_changed FROM mysql.global_priv ORDER BY User, Host
```

### `access.global_privileges`
```sql
SELECT grantee, GROUP_CONCAT(privilege_type ORDER BY privilege_type) AS privileges, MAX(is_grantable) AS grantable FROM information_schema.user_privileges GROUP BY grantee
```

### `access.password_lifetime`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('default_password_lifetime', 'disconnect_on_expired_password');
```

### `backup.binlog_retention`
Same rows as `ha_dr.binlog` (the collector reuses that result).

### `backup.backup_tooling_note`
Not a query: a reminder that this evidence comes from people and tooling outside the server.

### `cost.buffer_pool_vs_data`
```sql
SELECT @@innodb_buffer_pool_size AS buffer_pool_bytes, (SELECT SUM(data_length + index_length) FROM information_schema.tables WHERE engine = 'InnoDB') AS innodb_data_bytes
```

### `cost.fragmentation`
```sql
SELECT table_schema, table_name, data_free, data_length + index_length AS total_bytes FROM information_schema.tables WHERE data_free > 50*1024*1024 AND table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY data_free DESC LIMIT 25
```

### `cost.connections_vs_max`
```sql
SELECT (SELECT COUNT(*) FROM information_schema.processlist) AS current_connections, @@max_connections AS max_connections
```

### `cost.status_counters`
```sql
SHOW GLOBAL STATUS WHERE Variable_name IN ('Max_used_connections','Aborted_connects','Created_tmp_disk_tables','Innodb_buffer_pool_wait_free','Slow_queries','Threads_connected')
```

### `monitoring.settings`
```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('slow_query_log', 'long_query_time', 'log_queries_not_using_indexes', 'performance_schema', 'log_error', 'log_warnings', 'innodb_monitor_enable');
```

### `operations.long_running`
```sql
SELECT id, user, host, db, command, time, state, LEFT(info, 120) AS query FROM information_schema.processlist WHERE command NOT IN ('Sleep','Binlog Dump','Binlog Dump GTID') AND time > 300 ORDER BY time DESC LIMIT 20
```

### `operations.lock_waits`
First attempt (the collector falls back to the alternatives named above the catalogue when this fails):
```sql
SELECT COUNT(*) AS waiting FROM information_schema.innodb_lock_waits
```

### `operations.tables_without_pk`
```sql
SELECT t.table_schema, t.table_name, t.engine FROM information_schema.tables t WHERE t.table_type = 'BASE TABLE' AND t.table_schema NOT IN ('mysql','information_schema','performance_schema','sys') AND NOT EXISTS (SELECT 1 FROM information_schema.statistics s WHERE s.table_schema = t.table_schema AND s.table_name = t.table_name AND s.index_name = 'PRIMARY') ORDER BY 1,2 LIMIT 50
```

### `operations.myisam_tables`
```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE engine = 'MyISAM' AND table_schema NOT IN ('mysql','information_schema','performance_schema','sys') LIMIT 50
```
<!-- queries:end -->

## Reading the results

`ha_dr.binlog` with `log_bin` OFF means no replication and no point in time recovery. An empty `ha_dr.replica_status` with zero rows in `ha_dr.replicas_connected` means a single server. `security.ssl` with `have_ssl` DISABLED means clear text connections. `access.users` rows with host `%` accept connections from anywhere. `operations.myisam_tables` lists tables without crash recovery. `cost.buffer_pool_vs_data` compares memory to data; a pool far smaller than the InnoDB data on a busy server means disk reads.
