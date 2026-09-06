# PostgreSQL: read only access and the manual query catalogue

## The discovery role

Ask the owner to run this as a superuser. It grants monitoring views and settings, nothing that reads application rows.

```sql
CREATE ROLE discovery LOGIN PASSWORD 'choose a long password' VALID UNTIL '2026-12-31';
GRANT pg_monitor TO discovery;                       -- pg_read_all_settings, pg_read_all_stats, pg_stat_scan_tables
GRANT CONNECT ON DATABASE app TO discovery;          -- repeat per database you will discover
\c app
GRANT USAGE ON SCHEMA public TO discovery;           -- catalog reads only; no table SELECT is needed
GRANT EXECUTE ON FUNCTION pg_hba_file_rules() TO discovery;   -- per database; the view is superuser only by default
```

Tested on PostgreSQL 16: with `pg_monitor` alone every block collects except `security.hba`, which needs the EXECUTE grant above (the collector reports the exact error and the rule records an unknown until it is granted). Managed services (RDS, Cloud SQL, Azure) do not expose `pg_hba_file_rules`; record the service's network rules and authentication setting as the equivalent evidence.

On a standby, run the same command; `architecture.role` will report recovery mode and the replica rules adjust.

## Connection string

`postgresql://discovery:PASSWORD@host:5432/app?sslmode=require`. The password never appears in any output file; only the user name does.

## Manual query catalogue

When the collector cannot run, execute these in `psql` as the discovery role and paste the results under the same key in `evidence.json` (`{"ok": true, "sql": "...", "rows": [ {column: value}, ... ]}`), then run `python -m discovery assess --run runs/<name>`. This list is generated from `discovery/collectors_pg.py` by `python tools/render_queries.py`.

<!-- queries:start -->
### `inventory.version`
```sql
SELECT version() AS version, current_setting('server_version') AS server_version, pg_postmaster_start_time() AS started_at, now() - pg_postmaster_start_time() AS uptime
```

### `inventory.databases`
```sql
SELECT datname, pg_database_size(datname) AS size_bytes, pg_size_pretty(pg_database_size(datname)) AS size, datallowconn, datconnlimit, age(datfrozenxid) AS xid_age FROM pg_database WHERE NOT datistemplate ORDER BY size_bytes DESC
```

### `inventory.extensions`
```sql
SELECT extname, extversion FROM pg_extension ORDER BY extname
```

### `inventory.core_settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name IN ('data_directory', 'listen_addresses', 'port', 'max_connections', 'shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', 'timezone', 'server_encoding') ORDER BY name;
```

### `architecture.role`
```sql
SELECT pg_is_in_recovery() AS in_recovery
```

### `architecture.connections`
```sql
SELECT datname, usename, application_name, state, count(*) AS n FROM pg_stat_activity WHERE datname IS NOT NULL GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 50
```

### `architecture.largest_tables`
```sql
SELECT n.nspname AS schema, c.relname AS table, pg_total_relation_size(c.oid) AS total_bytes, pg_size_pretty(pg_total_relation_size(c.oid)) AS total, c.reltuples::bigint AS est_rows FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY total_bytes DESC LIMIT 25
```

### `architecture.logical_replication`
```sql
SELECT (SELECT count(*) FROM pg_publication) AS publications, (SELECT count(*) FROM pg_subscription) AS subscriptions
```

### `architecture.foreign_servers`
```sql
SELECT srvname, fdwname FROM pg_foreign_server s JOIN pg_foreign_data_wrapper w ON w.oid = s.srvfdw
```

### `ha_dr.replication`
```sql
SELECT client_addr, application_name, state, sync_state, write_lag, flush_lag, replay_lag FROM pg_stat_replication
```

### `ha_dr.settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name IN ('wal_level', 'archive_mode', 'archive_command', 'archive_timeout', 'max_wal_senders', 'wal_keep_size', 'synchronous_standby_names', 'synchronous_commit', 'hot_standby', 'primary_conninfo', 'restore_command') ORDER BY name;
```

### `ha_dr.archiver`
```sql
SELECT archived_count, last_archived_wal, last_archived_time, failed_count, last_failed_wal, last_failed_time FROM pg_stat_archiver
```

### `ha_dr.slots`
```sql
SELECT slot_name, slot_type, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal FROM pg_replication_slots
```

### `change_management.migration_tables`
```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('flyway_schema_history','schema_migrations','alembic_version','django_migrations','databasechangelog','knex_migrations','__EFMigrationsHistory','prisma_migrations','_prisma_migrations','goose_db_version') ORDER BY 1,2
```

### `change_management.ddl_logging`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name IN ('log_statement', 'log_min_duration_statement', 'log_line_prefix') ORDER BY name;
```

### `change_management.event_triggers`
```sql
SELECT evtname, evtevent, evtenabled FROM pg_event_trigger
```

### `security.ssl`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name IN ('ssl', 'ssl_cert_file', 'ssl_key_file', 'ssl_min_protocol_version', 'password_encryption', 'listen_addresses') ORDER BY name;
```

### `security.hba`
```sql
SELECT line_number, type, database, user_name, address, auth_method FROM pg_hba_file_rules ORDER BY line_number
```

### `security.ssl_connections`
```sql
SELECT ssl, count(*) AS n FROM pg_stat_ssl s JOIN pg_stat_activity a USING (pid) WHERE a.datname IS NOT NULL GROUP BY ssl
```

### `access.roles`
```sql
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, rolbypassrls, rolreplication, rolconnlimit, rolvaliduntil FROM pg_roles WHERE rolname NOT LIKE 'pg\_%' ORDER BY rolsuper DESC, rolname
```

### `access.public_schema`
```sql
SELECT nspname, nspacl FROM pg_namespace WHERE nspname = 'public'
```

### `access.db_acl`
```sql
SELECT datname, datacl FROM pg_database WHERE NOT datistemplate
```

### `backup.settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name IN ('archive_mode', 'archive_command', 'wal_level', 'checkpoint_timeout', 'max_wal_size', 'full_page_writes') ORDER BY name;
```

### `backup.archiver`
Same rows as `ha_dr.archiver` (the collector reuses that result).

### `backup.backup_tooling_note`
Not a query: a reminder that this evidence comes from people and tooling outside the server.

### `cost.cache_hit`
```sql
SELECT datname, blks_hit, blks_read, CASE WHEN blks_hit + blks_read = 0 THEN NULL ELSE round(100.0 * blks_hit / (blks_hit + blks_read), 2) END AS cache_hit_pct, temp_files, pg_size_pretty(temp_bytes) AS temp_bytes, deadlocks, stats_reset FROM pg_stat_database WHERE datname NOT LIKE 'template%' ORDER BY blks_read DESC
```

### `cost.unused_indexes`
```sql
SELECT s.schemaname, s.relname AS table, s.indexrelname AS index, s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid = s.indexrelid WHERE s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 25
```

### `cost.dead_tuples`
```sql
SELECT schemaname, relname, n_live_tup, n_dead_tup, CASE WHEN n_live_tup = 0 THEN NULL ELSE round(100.0 * n_dead_tup / n_live_tup, 1) END AS dead_pct, last_autovacuum, last_autoanalyze FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 25
```

### `cost.connections_vs_max`
```sql
SELECT (SELECT count(*) FROM pg_stat_activity) AS current_connections, current_setting('max_connections')::int AS max_connections
```

### `monitoring.settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name IN ('track_io_timing', 'track_activities', 'track_counts', 'log_min_duration_statement', 'log_checkpoints', 'log_lock_waits', 'log_autovacuum_min_duration', 'autovacuum', 'shared_preload_libraries', 'log_destination', 'logging_collector') ORDER BY name;
```

### `monitoring.pg_stat_statements`
```sql
SELECT count(*) AS installed FROM pg_extension WHERE extname = 'pg_stat_statements'
```

### `operations.long_running`
```sql
SELECT pid, datname, usename, state, now() - query_start AS running_for, left(query, 120) AS query FROM pg_stat_activity WHERE state <> 'idle' AND now() - query_start > interval '5 minutes' ORDER BY query_start LIMIT 20
```

### `operations.lock_waits`
```sql
SELECT count(*) AS waiting FROM pg_stat_activity WHERE wait_event_type = 'Lock'
```

### `operations.wraparound`
```sql
SELECT datname, age(datfrozenxid) AS xid_age, current_setting('autovacuum_freeze_max_age')::bigint AS freeze_max_age, round(100.0 * age(datfrozenxid) / current_setting('autovacuum_freeze_max_age')::bigint, 1) AS pct_of_limit FROM pg_database WHERE NOT datistemplate ORDER BY xid_age DESC
```

### `operations.invalid_indexes`
```sql
SELECT n.nspname, c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE NOT i.indisvalid
```

### `operations.tables_without_pk`
```sql
SELECT n.nspname AS schema, c.relname AS table FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') ORDER BY 1,2 LIMIT 50
```
<!-- queries:end -->

## Reading the results

`ha_dr.replication` empty on a primary means no standby. `backup.settings` with `archive_mode` off means no point in time recovery from this server. `security.hba` rows with `trust` on `host` lines mean password free network logins. `access.roles` with `rolsuper` true beyond `postgres` means extra superusers. `cost.unused_indexes` is only meaningful when `stats_reset` in `cost.cache_hit` is older than one business cycle. `operations.wraparound` `pct_of_limit` over 50 needs attention this month, over 80 this week.
