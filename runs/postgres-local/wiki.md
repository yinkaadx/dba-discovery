# Database discovery: PostgreSQL at 127.0.0.1:5432
Run `postgres-local`, evidence collected 2026-09-06 04:51 UTC with the read only account `discovery`. Every statement below cites an evidence key; the appendix holds the query and the rows returned so anyone can rerun it.

## 1. Summary
| Item | Value |
| --- | --- |
| Version | PostgreSQL 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit |
| Started | 2026-09-06 04:32:19.508837+00:00 (uptime 0:18:49.016104) |
| Role | primary |
| Databases | 3 (importer_demo 8575 kB, proofdb 7599 kB, postgres 7503 kB); total 23 MB |
| Extensions | plpgsql 1.0 |
| Connections | 6 of max_connections 100 |
| Streaming replicas | 0 |

| Severity | Findings |
| --- | --- |
| High | 2 |
| Medium | 3 |
| Low | 6 |
| Info | 1 |
| Unknowns | 1 |

### Top actions
1. **WAL archiving is off** (High, medium effort): Enable archive_mode with an archive_command or a backup tool that manages WAL (pgBackRest, Barman, or the cloud provider's PITR), then run a timed restore test.
2. **Single primary with no streaming replica** (High, large effort): Add a hot standby (streaming replication with a replication slot) and a tested promotion procedure; decide the target recovery time with the business first.
3. **pg_stat_statements is not installed** (Medium, small effort): Add pg_stat_statements to shared_preload_libraries (restart) and CREATE EXTENSION it in each database.
4. **Slow statements are not logged** (Medium, small effort): Set log_min_duration_statement to a value such as 1000 ms (no restart) and review the log weekly.
5. **No schema migration history table found** (Medium, medium effort): Adopt one migration tool and put every DDL change in version control with a review step; start by baselining the current schema.

## 2. Findings by area
### 2.1 Database and platform inventory
Evidence reviewed: `inventory.version`, `inventory.databases`, `inventory.extensions`, `inventory.core_settings`.

No finding in this area from the evidence collected.

### 2.2 Architecture and data flow
Evidence reviewed: `architecture.role`, `architecture.connections`, `architecture.largest_tables`, `architecture.logical_replication`, `architecture.foreign_servers`.

No finding in this area from the evidence collected.

### 2.3 High availability and disaster recovery
Evidence reviewed: `ha_dr.replication`, `ha_dr.settings`, `ha_dr.archiver`, `ha_dr.slots`.

**`PG-HA-001` Single primary with no streaming replica** (High)  
What the evidence shows: pg_stat_replication returned no rows and the server is not in recovery, so a host failure means downtime until a restore completes.  
Recommendation: Add a hot standby (streaming replication with a replication slot) and a tested promotion procedure; decide the target recovery time with the business first. Effort: large. Evidence: `ha_dr.replication`, `architecture.role`.

### 2.4 Database change management and release processes
Evidence reviewed: `change_management.migration_tables`, `change_management.ddl_logging`, `change_management.event_triggers`.

**`PG-CHG-001` No schema migration history table found** (Medium)  
What the evidence shows: None of the common migration tools (Flyway, Liquibase, Alembic, Django, Prisma, Knex, goose, EF) left a history table, so schema changes are probably applied by hand.  
Recommendation: Adopt one migration tool and put every DDL change in version control with a review step; start by baselining the current schema. Effort: medium. Evidence: `change_management.migration_tables`.

**`PG-CHG-002` DDL is not logged** (Low)  
What the evidence shows: log_statement is none and there are no event triggers, so there is no record of who changed the schema and when.  
Recommendation: Set log_statement to ddl (no restart needed) so every schema change lands in the server log. Effort: small. Evidence: `change_management.ddl_logging`, `change_management.event_triggers`.

### 2.5 Security configuration and encryption
Evidence reviewed: `security.ssl`, `security.hba`, `security.ssl_connections`.

No finding in this area from the evidence collected.

### 2.6 User access and authentication
Evidence reviewed: `access.roles`, `access.public_schema`, `access.db_acl`.

**`PG-ACC-001` Login roles have no password expiry** (Low)  
What the evidence shows: 2 login role(s) have no VALID UNTIL date: discovery, importer.  
Recommendation: Decide a rotation period for human accounts and set VALID UNTIL; keep service accounts on vault managed rotation. Effort: small. Evidence: `access.roles`.

### 2.7 Backup and retention policies
Evidence reviewed: `backup.settings`, `backup.archiver`, `backup.backup_tooling_note`.

**`PG-BKP-001` WAL archiving is off** (High)  
What the evidence shows: archive_mode is off, so point in time recovery is not possible from this server; recovery is limited to the last full backup taken by external tooling.  
Recommendation: Enable archive_mode with an archive_command or a backup tool that manages WAL (pgBackRest, Barman, or the cloud provider's PITR), then run a timed restore test. Effort: medium. Evidence: `backup.settings`.

Unknown: Backup schedule, retention and the date of the last successful restore test. How to obtain: Ask the operations owner for the backup job definition, retention policy and restore test log; the database cannot report these.

### 2.8 Cloud cost and resource usage
Evidence reviewed: `cost.cache_hit`, `cost.unused_indexes`, `cost.dead_tuples`, `cost.connections_vs_max`.

**`PG-CST-001` 2 index(es) have never been scanned** (Low)  
What the evidence shows: Indexes with zero scans since statistics reset cost write time and disk: orders_status_idx (16 kB), ix_import_runs_hash (16 kB).  
Recommendation: Confirm the statistics window covers a full business cycle, then drop the unused ones with DROP INDEX CONCURRENTLY. Effort: small. Evidence: `cost.unused_indexes`.

### 2.9 Monitoring and observability
Evidence reviewed: `monitoring.settings`, `monitoring.pg_stat_statements`.

**`PG-MON-001` pg_stat_statements is not installed** (Medium)  
What the evidence shows: Without it there is no per query view of time, calls and I/O, so slow query work is guesswork.  
Recommendation: Add pg_stat_statements to shared_preload_libraries (restart) and CREATE EXTENSION it in each database. Effort: small. Evidence: `monitoring.pg_stat_statements`.

**`PG-MON-002` Slow statements are not logged** (Medium)  
What the evidence shows: log_min_duration_statement is `-1`, so no statement is ever written to the log by duration.  
Recommendation: Set log_min_duration_statement to a value such as 1000 ms (no restart) and review the log weekly. Effort: small. Evidence: `monitoring.settings`.

**`PG-MON-003` track_io_timing is off** (Low)  
What the evidence shows: I/O time per query is not recorded, which removes a cheap diagnostic.  
Recommendation: Set track_io_timing to on; the cost is negligible on modern hardware. Effort: small. Evidence: `monitoring.settings`.

**`PG-MON-004` log_lock_waits is off** (Low)  
What the evidence shows: lock waits over deadlock_timeout are not logged, which removes a cheap diagnostic.  
Recommendation: Set log_lock_waits to on; the cost is negligible on modern hardware. Effort: small. Evidence: `monitoring.settings`.

**`PG-MON-005` Server log relies on the service wrapper** (Info)  
What the evidence shows: logging_collector is off and log_destination is not syslog; on Debian and Ubuntu packages the cluster wrapper captures stderr into /var/log/postgresql, on other installs the lines may be lost.  
Recommendation: Confirm where the log lands and that it rotates; otherwise enable logging_collector with daily rotation or route to syslog or the cloud log service. Effort: small. Evidence: `monitoring.settings`.

### 2.10 Outstanding database concerns and operational issues
Evidence reviewed: `operations.long_running`, `operations.lock_waits`, `operations.wraparound`, `operations.invalid_indexes`, `operations.tables_without_pk`.

**`PG-OPS-001` 1 table(s) have no primary key** (Low)  
What the evidence shows: Tables without a primary key cannot be logically replicated by default and make upserts and deduplication awkward: public.audit_log.  
Recommendation: Add a surrogate or natural primary key to each, starting with the largest. Effort: small. Evidence: `operations.tables_without_pk`.

## 3. Unknowns and how to obtain them
| Area | Question | How to obtain |
| --- | --- | --- |
| Backup and retention policies | Backup schedule, retention and the date of the last successful restore test | Ask the operations owner for the backup job definition, retention policy and restore test log; the database cannot report these |

## 4. Prioritized recommendations
Order: severity first, then the smallest effort first, so quick high value fixes come before long projects.

| Priority | Id | Action | Severity | Effort | Area | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `PG-BKP-001` | Enable archive_mode with an archive_command or a backup tool that manages WAL (pgBackRest, Barman, or the cloud provider's PITR), then run a timed restore test. | High | Medium | Backup and retention policies | `backup.settings` |
| 2 | `PG-HA-001` | Add a hot standby (streaming replication with a replication slot) and a tested promotion procedure; decide the target recovery time with the business first. | High | Large | High availability and disaster recovery | `ha_dr.replication`, `architecture.role` |
| 3 | `PG-MON-001` | Add pg_stat_statements to shared_preload_libraries (restart) and CREATE EXTENSION it in each database. | Medium | Small | Monitoring and observability | `monitoring.pg_stat_statements` |
| 4 | `PG-MON-002` | Set log_min_duration_statement to a value such as 1000 ms (no restart) and review the log weekly. | Medium | Small | Monitoring and observability | `monitoring.settings` |
| 5 | `PG-CHG-001` | Adopt one migration tool and put every DDL change in version control with a review step; start by baselining the current schema. | Medium | Medium | Database change management and release processes | `change_management.migration_tables` |
| 6 | `PG-ACC-001` | Decide a rotation period for human accounts and set VALID UNTIL; keep service accounts on vault managed rotation. | Low | Small | User access and authentication | `access.roles` |
| 7 | `PG-CHG-002` | Set log_statement to ddl (no restart needed) so every schema change lands in the server log. | Low | Small | Database change management and release processes | `change_management.ddl_logging`, `change_management.event_triggers` |
| 8 | `PG-CST-001` | Confirm the statistics window covers a full business cycle, then drop the unused ones with DROP INDEX CONCURRENTLY. | Low | Small | Cloud cost and resource usage | `cost.unused_indexes` |
| 9 | `PG-MON-003` | Set track_io_timing to on; the cost is negligible on modern hardware. | Low | Small | Monitoring and observability | `monitoring.settings` |
| 10 | `PG-MON-004` | Set log_lock_waits to on; the cost is negligible on modern hardware. | Low | Small | Monitoring and observability | `monitoring.settings` |
| 11 | `PG-OPS-001` | Add a surrogate or natural primary key to each, starting with the largest. | Low | Small | Outstanding database concerns and operational issues | `operations.tables_without_pk` |
| 12 | `PG-MON-005` | Confirm where the log lands and that it rotates; otherwise enable logging_collector with daily rotation or route to syslog or the cloud log service. | Info | Small | Monitoring and observability | `monitoring.settings` |

## Appendix A: Evidence
Each block is the query that was run and the rows it returned at collection time. A block marked failed records the server's error so the missing permission can be granted and the check rerun.

### Database and platform inventory
#### `inventory.version`
```sql
SELECT version() AS version, current_setting('server_version') AS server_version, pg_postmaster_start_time() AS started_at, now() - pg_postmaster_start_time() AS uptime
```
| version | server_version | started_at | uptime |
| --- | --- | --- | --- |
| PostgreSQL 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit | 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1) | 2026-09-06 04:32:19.508837+00:00 | 0:18:49.016104 |

#### `inventory.databases`
```sql
SELECT datname, pg_database_size(datname) AS size_bytes, pg_size_pretty(pg_database_size(datname)) AS size, datallowconn, datconnlimit, age(datfrozenxid) AS xid_age FROM pg_database WHERE NOT datistemplate ORDER BY size_bytes DESC
```
| datname | size_bytes | size | datallowconn | datconnlimit | xid_age |
| --- | --- | --- | --- | --- | --- |
| importer_demo | 8780823 | 8575 kB | true | -1 | 138 |
| proofdb | 7781399 | 7599 kB | true | -1 | 138 |
| postgres | 7683095 | 7503 kB | true | -1 | 138 |

#### `inventory.extensions`
```sql
SELECT extname, extversion FROM pg_extension ORDER BY extname
```
| extname | extversion |
| --- | --- |
| plpgsql | 1.0 |

#### `inventory.core_settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name
```
| name | setting | unit | source |
| --- | --- | --- | --- |
| data_directory | /var/lib/postgresql/16/main |  | override |
| effective_cache_size | 524288 | 8kB | default |
| listen_addresses | localhost |  | default |
| maintenance_work_mem | 65536 | kB | default |
| max_connections | 100 |  | configuration file |
| port | 5432 |  | configuration file |
| server_encoding | UTF8 |  | default |
| shared_buffers | 16384 | 8kB | configuration file |
| work_mem | 4096 | kB | default |

### Architecture and data flow
#### `architecture.role`
```sql
SELECT pg_is_in_recovery() AS in_recovery
```
| in_recovery |
| --- |
| false |

#### `architecture.connections`
```sql
SELECT datname, usename, application_name, state, count(*) AS n FROM pg_stat_activity WHERE datname IS NOT NULL GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 50
```
| datname | usename | application_name | state | n |
| --- | --- | --- | --- | --- |
| importer_demo | discovery |  | active | 1 |

#### `architecture.largest_tables`
```sql
SELECT n.nspname AS schema, c.relname AS table, pg_total_relation_size(c.oid) AS total_bytes, pg_size_pretty(pg_total_relation_size(c.oid)) AS total, c.reltuples::bigint AS est_rows FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY total_bytes DESC LIMIT 25
```
| schema | table | total_bytes | total | est_rows |
| --- | --- | --- | --- | --- |
| public | orders | 65536 | 64 kB | 4 |
| public | customers | 49152 | 48 kB | -1 |
| public | import_runs | 49152 | 48 kB | -1 |
| public | import_rejects | 32768 | 32 kB | -1 |
| public | audit_log | 16384 | 16 kB | -1 |

#### `architecture.logical_replication`
```sql
SELECT (SELECT count(*) FROM pg_publication) AS publications, (SELECT count(*) FROM pg_subscription) AS subscriptions
```
| publications | subscriptions |
| --- | --- |
| 0 | 0 |

#### `architecture.foreign_servers`
```sql
SELECT srvname, fdwname FROM pg_foreign_server s JOIN pg_foreign_data_wrapper w ON w.oid = s.srvfdw
```
_no rows_

### High availability and disaster recovery
#### `ha_dr.replication`
```sql
SELECT client_addr, application_name, state, sync_state, write_lag, flush_lag, replay_lag FROM pg_stat_replication
```
_no rows_

#### `ha_dr.settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name
```
| name | setting | unit | source |
| --- | --- | --- | --- |
| archive_command | (disabled) |  | default |
| archive_mode | off |  | default |
| archive_timeout | 0 | s | default |
| hot_standby | on |  | default |
| max_wal_senders | 10 |  | default |
| primary_conninfo |  |  | default |
| restore_command |  |  | default |
| synchronous_commit | on |  | default |
| synchronous_standby_names |  |  | default |
| wal_keep_size | 0 | MB | default |
| wal_level | replica |  | default |

#### `ha_dr.archiver`
```sql
SELECT archived_count, last_archived_wal, last_archived_time, failed_count, last_failed_wal, last_failed_time FROM pg_stat_archiver
```
| archived_count | last_archived_wal | last_archived_time | failed_count | last_failed_wal | last_failed_time |
| --- | --- | --- | --- | --- | --- |
| 0 |  |  | 0 |  |  |

#### `ha_dr.slots`
```sql
SELECT slot_name, slot_type, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal FROM pg_replication_slots
```
_no rows_

### Database change management and release processes
#### `change_management.migration_tables`
```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('flyway_schema_history','schema_migrations','alembic_version','django_migrations','databasechangelog','knex_migrations','__EFMigrationsHistory','prisma_migrations','_prisma_migrations','goose_db_version') ORDER BY 1,2
```
_no rows_

#### `change_management.ddl_logging`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name
```
| name | setting | unit | source |
| --- | --- | --- | --- |
| log_line_prefix | %m [%p] %q%u@%d |  | configuration file |
| log_min_duration_statement | -1 | ms | default |
| log_statement | none |  | default |

#### `change_management.event_triggers`
```sql
SELECT evtname, evtevent, evtenabled FROM pg_event_trigger
```
_no rows_

### Security configuration and encryption
#### `security.ssl`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name
```
| name | setting | unit | source |
| --- | --- | --- | --- |
| listen_addresses | localhost |  | default |
| password_encryption | scram-sha-256 |  | default |
| ssl | on |  | configuration file |
| ssl_cert_file | /etc/ssl/certs/ssl-cert-snakeoil.pem |  | configuration file |
| ssl_key_file | /etc/ssl/private/ssl-cert-snakeoil.key |  | configuration file |
| ssl_min_protocol_version | TLSv1.2 |  | default |

#### `security.hba`
```sql
SELECT line_number, type, database, user_name, address, auth_method FROM pg_hba_file_rules ORDER BY line_number
```
| line_number | type | database | user_name | address | auth_method |
| --- | --- | --- | --- | --- | --- |
| 118 | local | all | postgres |  | peer |
| 123 | local | all | all |  | peer |
| 125 | host | all | all | 127.0.0.1 | scram-sha-256 |
| 127 | host | all | all | ::1 | scram-sha-256 |
| 130 | local | replication | all |  | peer |
| 131 | host | replication | all | 127.0.0.1 | scram-sha-256 |
| 132 | host | replication | all | ::1 | scram-sha-256 |

#### `security.ssl_connections`
```sql
SELECT ssl, count(*) AS n FROM pg_stat_ssl s JOIN pg_stat_activity a USING (pid) WHERE a.datname IS NOT NULL GROUP BY ssl
```
| ssl | n |
| --- | --- |
| true | 1 |

### User access and authentication
#### `access.roles`
```sql
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, rolbypassrls, rolreplication, rolconnlimit, rolvaliduntil FROM pg_roles WHERE rolname NOT LIKE 'pg\_%' ORDER BY rolsuper DESC, rolname
```
| rolname | rolsuper | rolcreaterole | rolcreatedb | rolcanlogin | rolbypassrls | rolreplication | rolconnlimit | rolvaliduntil |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| postgres | true | true | true | true | true | true | -1 |  |
| discovery | false | false | false | true | false | false | -1 |  |
| importer | false | false | false | true | false | false | -1 |  |

#### `access.public_schema`
```sql
SELECT nspname, nspacl FROM pg_namespace WHERE nspname = 'public'
```
| nspname | nspacl |
| --- | --- |
| public | pg_database_owner=UC/pg_database_owner, =U/pg_database_owner, discovery=U/pg_database_owner |

#### `access.db_acl`
```sql
SELECT datname, datacl FROM pg_database WHERE NOT datistemplate
```
| datname | datacl |
| --- | --- |
| postgres |  |
| importer_demo | =Tc/importer, importer=CTc/importer, discovery=c/importer |
| proofdb | =Tc/postgres, postgres=CTc/postgres, discovery=c/postgres |

### Backup and retention policies
#### `backup.settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name
```
| name | setting | unit | source |
| --- | --- | --- | --- |
| archive_command | (disabled) |  | default |
| archive_mode | off |  | default |
| checkpoint_timeout | 300 | s | default |
| full_page_writes | on |  | default |
| max_wal_size | 1024 | MB | configuration file |
| wal_level | replica |  | default |

#### `backup.archiver`
```sql
SELECT archived_count, last_archived_wal, last_archived_time, failed_count, last_failed_wal, last_failed_time FROM pg_stat_archiver
```
| archived_count | last_archived_wal | last_archived_time | failed_count | last_failed_wal | last_failed_time |
| --- | --- | --- | --- | --- | --- |
| 0 |  |  | 0 |  |  |

#### `backup.backup_tooling_note`
| note |
| --- |
| Backup jobs, retention and restore tests live outside the database; request the backup schedule, retention policy and the last restore test record |

### Cloud cost and resource usage
#### `cost.cache_hit`
```sql
SELECT datname, blks_hit, blks_read, CASE WHEN blks_hit + blks_read = 0 THEN NULL ELSE round(100.0 * blks_hit / (blks_hit + blks_read), 2) END AS cache_hit_pct, temp_files, pg_size_pretty(temp_bytes) AS temp_bytes, deadlocks, stats_reset FROM pg_stat_database WHERE datname NOT LIKE 'template%' ORDER BY blks_read DESC
```
| datname | blks_hit | blks_read | cache_hit_pct | temp_files | temp_bytes | deadlocks | stats_reset |
| --- | --- | --- | --- | --- | --- | --- | --- |
| importer_demo | 21070 | 355 | 98.34 | 0 | 0 bytes | 0 |  |
| postgres | 3492 | 147 | 95.96 | 0 | 0 bytes | 0 |  |
| proofdb | 3176 | 147 | 95.58 | 0 | 0 bytes | 0 |  |

#### `cost.unused_indexes`
```sql
SELECT s.schemaname, s.relname AS table, s.indexrelname AS index, s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid = s.indexrelid WHERE s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 25
```
| schemaname | table | index | idx_scan | size |
| --- | --- | --- | --- | --- |
| public | orders | orders_status_idx | 0 | 16 kB |
| public | import_runs | ix_import_runs_hash | 0 | 16 kB |

#### `cost.dead_tuples`
```sql
SELECT schemaname, relname, n_live_tup, n_dead_tup, CASE WHEN n_live_tup = 0 THEN NULL ELSE round(100.0 * n_dead_tup / n_live_tup, 1) END AS dead_pct, last_autovacuum, last_autoanalyze FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 25
```
| schemaname | relname | n_live_tup | n_dead_tup | dead_pct | last_autovacuum | last_autoanalyze |
| --- | --- | --- | --- | --- | --- | --- |
| public | import_rejects | 0 | 0 |  |  |  |
| public | orders | 0 | 0 |  |  |  |
| public | customers | 0 | 0 |  |  |  |
| public | audit_log | 3 | 0 | 0.0 |  |  |
| public | import_runs | 0 | 0 |  |  |  |

#### `cost.connections_vs_max`
```sql
SELECT (SELECT count(*) FROM pg_stat_activity) AS current_connections, current_setting('max_connections')::int AS max_connections
```
| current_connections | max_connections |
| --- | --- |
| 6 | 100 |

### Monitoring and observability
#### `monitoring.settings`
```sql
SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name
```
| name | setting | unit | source |
| --- | --- | --- | --- |
| autovacuum | on |  | default |
| log_autovacuum_min_duration | 600000 | ms | default |
| log_checkpoints | on |  | default |
| log_destination | stderr |  | default |
| log_lock_waits | off |  | default |
| log_min_duration_statement | -1 | ms | default |
| logging_collector | off |  | default |
| shared_preload_libraries |  |  | default |
| track_activities | on |  | default |
| track_counts | on |  | default |
| track_io_timing | off |  | default |

#### `monitoring.pg_stat_statements`
```sql
SELECT count(*) AS installed FROM pg_extension WHERE extname = 'pg_stat_statements'
```
| installed |
| --- |
| 0 |

### Outstanding database concerns and operational issues
#### `operations.long_running`
```sql
SELECT pid, datname, usename, state, now() - query_start AS running_for, left(query, 120) AS query FROM pg_stat_activity WHERE state <> 'idle' AND now() - query_start > interval '5 minutes' ORDER BY query_start LIMIT 20
```
_no rows_

#### `operations.lock_waits`
```sql
SELECT count(*) AS waiting FROM pg_stat_activity WHERE wait_event_type = 'Lock'
```
| waiting |
| --- |
| 0 |

#### `operations.wraparound`
```sql
SELECT datname, age(datfrozenxid) AS xid_age, current_setting('autovacuum_freeze_max_age')::bigint AS freeze_max_age, round(100.0 * age(datfrozenxid) / current_setting('autovacuum_freeze_max_age')::bigint, 1) AS pct_of_limit FROM pg_database WHERE NOT datistemplate ORDER BY xid_age DESC
```
| datname | xid_age | freeze_max_age | pct_of_limit |
| --- | --- | --- | --- |
| postgres | 138 | 200000000 | 0.0 |
| importer_demo | 138 | 200000000 | 0.0 |
| proofdb | 138 | 200000000 | 0.0 |

#### `operations.invalid_indexes`
```sql
SELECT n.nspname, c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE NOT i.indisvalid
```
_no rows_

#### `operations.tables_without_pk`
```sql
SELECT n.nspname AS schema, c.relname AS table FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'p') ORDER BY 1,2 LIMIT 50
```
| schema | table |
| --- | --- |
| public | audit_log |

