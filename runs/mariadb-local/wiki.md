# Database discovery: MySQL or MariaDB at 127.0.0.1:3306
Run `mariadb-local`, evidence collected 2026-09-06 04:42 UTC with the read only account `discovery`. Every statement below cites an evidence key; the appendix holds the query and the rows returned so anyone can rerun it.

## 1. Summary
| Item | Value |
| --- | --- |
| Version | 10.11.14-MariaDB-0ubuntu0.24.04.1 (Ubuntu 24.04) on vm:3306 |
| Uptime | 0 d 0 h |
| Schemas | 2 (glpi 442 tables, shopdemo 2 tables); data 46 MB |
| Storage engines | InnoDB 443, MyISAM 1 |
| Connections | 1 of max_connections 151 |
| Replicas connected | 0 |

| Severity | Findings |
| --- | --- |
| High | 3 |
| Medium | 5 |
| Low | 3 |
| Info | 0 |
| Unknowns | 1 |

### Top actions
1. **Binary logging is off** (High, small effort): Enable log_bin with binlog_format ROW, set an expiry (binlog_expire_logs_seconds or expire_logs_days) and sync_binlog 1; restart required.
2. **TLS is not available on the server** (High, small effort): Install a certificate (ssl_ca, ssl_cert, ssl_key), restart, then set require_secure_transport ON once clients are verified.
3. **Single server with no replica** (High, large effort): Add a replica (asynchronous or semi synchronous) and a documented promotion procedure; agree the recovery time objective with the business first.
4. **Accounts accept connections from any host** (Medium, small effort): Limit each account's host to the application subnet; the firewall should not be the only control.
5. **Slow query log is off** (Medium, small effort): Set slow_query_log ON with long_query_time around 1 second and review with `pt-query-digest` or the Performance Schema.

## 2. Findings by area
### 2.1 Database and platform inventory
Evidence reviewed: `inventory.version`, `inventory.uptime`, `inventory.databases`, `inventory.engines`, `inventory.core_settings`.

No finding in this area from the evidence collected.

### 2.2 Architecture and data flow
Evidence reviewed: `architecture.connections`, `architecture.largest_tables`, `architecture.server_id`.

No finding in this area from the evidence collected.

### 2.3 High availability and disaster recovery
Evidence reviewed: `ha_dr.binlog`, `ha_dr.replica_status`, `ha_dr.replicas_connected`.

**`MY-HA-001` Binary logging is off** (High)  
What the evidence shows: log_bin is OFF, so replication cannot be set up and point in time recovery between backups is impossible.  
Recommendation: Enable log_bin with binlog_format ROW, set an expiry (binlog_expire_logs_seconds or expire_logs_days) and sync_binlog 1; restart required. Effort: small. Evidence: `ha_dr.binlog`.

**`MY-HA-002` Single server with no replica** (High)  
What the evidence shows: SHOW REPLICA STATUS is empty and no replica is connected, so a host failure means downtime until a restore completes.  
Recommendation: Add a replica (asynchronous or semi synchronous) and a documented promotion procedure; agree the recovery time objective with the business first. Effort: large. Evidence: `ha_dr.replica_status`, `ha_dr.replicas_connected`.

### 2.4 Database change management and release processes
Evidence reviewed: `change_management.migration_tables`, `change_management.ddl_logging`.

**`MY-CHG-001` No schema migration history table found** (Medium)  
What the evidence shows: No migration tool history table exists, so schema changes are probably applied by hand.  
Recommendation: Adopt one migration tool and put every DDL change in version control with a review step; baseline the current schema first. Effort: medium. Evidence: `change_management.migration_tables`.

### 2.5 Security configuration and encryption
Evidence reviewed: `security.ssl`, `security.auth_plugins`, `security.local_infile`.

**`MY-SEC-001` TLS is not available on the server** (High)  
What the evidence shows: have_ssl is DISABLED, so every network client sends credentials and data in clear text.  
Recommendation: Install a certificate (ssl_ca, ssl_cert, ssl_key), restart, then set require_secure_transport ON once clients are verified. Effort: small. Evidence: `security.ssl`.

**`MY-SEC-002` local_infile is enabled** (Medium)  
What the evidence shows: A compromised or malicious server can read files from a connecting client's file system through LOAD DATA LOCAL.  
Recommendation: Set local_infile OFF unless a specific loader needs it, and then limit it to that user. Effort: small. Evidence: `security.local_infile`.

**`MY-SEC-003` Host name resolution is on for connections** (Low)  
What the evidence shows: skip_name_resolve is OFF; DNS delays slow connections and grants keyed on host names depend on DNS being trustworthy.  
Recommendation: Turn skip_name_resolve ON and convert host based grants to IP ranges. Effort: small. Evidence: `security.local_infile`.

### 2.6 User access and authentication
Evidence reviewed: `access.users`, `access.global_privileges`, `access.password_lifetime`.

**`MY-ACC-001` Accounts accept connections from any host** (Medium)  
What the evidence shows: app@%  
Recommendation: Limit each account's host to the application subnet; the firewall should not be the only control. Effort: small. Evidence: `access.users`.

**`MY-ACC-002` Passwords never expire by default** (Low)  
What the evidence shows: default_password_lifetime is 0.  
Recommendation: Set a lifetime for human accounts and exempt service accounts explicitly (ALTER USER ... PASSWORD EXPIRE NEVER). Effort: small. Evidence: `access.password_lifetime`.

### 2.7 Backup and retention policies
Evidence reviewed: `backup.binlog_retention`, `backup.backup_tooling_note`.

No finding in this area from the evidence collected.

Unknown: Backup schedule, retention and the date of the last successful restore test. How to obtain: Ask the operations owner for the backup job (mysqldump, mariabackup, xtrabackup or snapshots), retention and restore test log; the server cannot report these.

### 2.8 Cloud cost and resource usage
Evidence reviewed: `cost.buffer_pool_vs_data`, `cost.fragmentation`, `cost.connections_vs_max`, `cost.status_counters`.

No finding in this area from the evidence collected.

### 2.9 Monitoring and observability
Evidence reviewed: `monitoring.settings`.

**`MY-MON-001` Slow query log is off** (Medium)  
What the evidence shows: No record of slow statements exists, so performance work has no evidence to start from.  
Recommendation: Set slow_query_log ON with long_query_time around 1 second and review with `pt-query-digest` or the Performance Schema. Effort: small. Evidence: `monitoring.settings`.

**`MY-MON-002` Performance Schema is off** (Low)  
What the evidence shows: Per statement and wait event instrumentation is unavailable.  
Recommendation: Enable performance_schema (restart) with the default instruments. Effort: small. Evidence: `monitoring.settings`.

### 2.10 Outstanding database concerns and operational issues
Evidence reviewed: `operations.long_running`, `operations.lock_waits`, `operations.tables_without_pk`, `operations.myisam_tables`.

**`MY-OPS-001` 1 MyISAM table(s) in application schemas** (Medium)  
What the evidence shows: MyISAM has no crash recovery, no transactions and table level locks: shopdemo.legacy_log.  
Recommendation: Convert to InnoDB (ALTER TABLE ... ENGINE=InnoDB) after checking for FULLTEXT or spatial features that need attention. Effort: medium. Evidence: `operations.myisam_tables`.

## 3. Unknowns and how to obtain them
| Area | Question | How to obtain |
| --- | --- | --- |
| Backup and retention policies | Backup schedule, retention and the date of the last successful restore test | Ask the operations owner for the backup job (mysqldump, mariabackup, xtrabackup or snapshots), retention and restore test log; the server cannot report these |

## 4. Prioritized recommendations
Order: severity first, then the smallest effort first, so quick high value fixes come before long projects.

| Priority | Id | Action | Severity | Effort | Area | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `MY-HA-001` | Enable log_bin with binlog_format ROW, set an expiry (binlog_expire_logs_seconds or expire_logs_days) and sync_binlog 1; restart required. | High | Small | High availability and disaster recovery | `ha_dr.binlog` |
| 2 | `MY-SEC-001` | Install a certificate (ssl_ca, ssl_cert, ssl_key), restart, then set require_secure_transport ON once clients are verified. | High | Small | Security configuration and encryption | `security.ssl` |
| 3 | `MY-HA-002` | Add a replica (asynchronous or semi synchronous) and a documented promotion procedure; agree the recovery time objective with the business first. | High | Large | High availability and disaster recovery | `ha_dr.replica_status`, `ha_dr.replicas_connected` |
| 4 | `MY-ACC-001` | Limit each account's host to the application subnet; the firewall should not be the only control. | Medium | Small | User access and authentication | `access.users` |
| 5 | `MY-MON-001` | Set slow_query_log ON with long_query_time around 1 second and review with `pt-query-digest` or the Performance Schema. | Medium | Small | Monitoring and observability | `monitoring.settings` |
| 6 | `MY-SEC-002` | Set local_infile OFF unless a specific loader needs it, and then limit it to that user. | Medium | Small | Security configuration and encryption | `security.local_infile` |
| 7 | `MY-CHG-001` | Adopt one migration tool and put every DDL change in version control with a review step; baseline the current schema first. | Medium | Medium | Database change management and release processes | `change_management.migration_tables` |
| 8 | `MY-OPS-001` | Convert to InnoDB (ALTER TABLE ... ENGINE=InnoDB) after checking for FULLTEXT or spatial features that need attention. | Medium | Medium | Outstanding database concerns and operational issues | `operations.myisam_tables` |
| 9 | `MY-ACC-002` | Set a lifetime for human accounts and exempt service accounts explicitly (ALTER USER ... PASSWORD EXPIRE NEVER). | Low | Small | User access and authentication | `access.password_lifetime` |
| 10 | `MY-MON-002` | Enable performance_schema (restart) with the default instruments. | Low | Small | Monitoring and observability | `monitoring.settings` |
| 11 | `MY-SEC-003` | Turn skip_name_resolve ON and convert host based grants to IP ranges. | Low | Small | Security configuration and encryption | `security.local_infile` |

## Appendix A: Evidence
Each block is the query that was run and the rows it returned at collection time. A block marked failed records the server's error so the missing permission can be granted and the check rerun.

### Database and platform inventory
#### `inventory.version`
```sql
SELECT VERSION() AS version, @@version_comment AS flavour, @@hostname AS host, @@port AS port
```
| version | flavour | host | port |
| --- | --- | --- | --- |
| 10.11.14-MariaDB-0ubuntu0.24.04.1 | Ubuntu 24.04 | vm | 3306 |

#### `inventory.uptime`
```sql
SHOW GLOBAL STATUS LIKE 'Uptime'
```
| Variable_name | Value |
| --- | --- |
| Uptime | 875 |

#### `inventory.databases`
```sql
SELECT table_schema AS db, ROUND(SUM(data_length + index_length)) AS size_bytes, COUNT(*) AS tables FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY table_schema ORDER BY size_bytes DESC
```
| db | size_bytes | tables |
| --- | --- | --- |
| glpi | 48578560.0 | 442 |
| shopdemo | 115712.0 | 2 |

#### `inventory.engines`
```sql
SELECT engine, COUNT(*) AS tables FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') GROUP BY engine
```
| engine | tables |
| --- | --- |
| InnoDB | 443 |
| MyISAM | 1 |

#### `inventory.core_settings`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| character_set_server | utf8mb4 |
| collation_server | utf8mb4_general_ci |
| datadir | /var/lib/mysql/ |
| innodb_buffer_pool_size | 134217728 |
| innodb_file_per_table | ON |
| max_connections | 151 |
| sql_mode | STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION |
| time_zone | SYSTEM |

### Architecture and data flow
#### `architecture.connections`
```sql
SELECT user, host, db, command, COUNT(*) AS n FROM information_schema.processlist GROUP BY 1,2,3,4 ORDER BY n DESC LIMIT 50
```
| user | host | db | command | n |
| --- | --- | --- | --- | --- |
| discovery | localhost:60880 | shopdemo | Query | 1 |

#### `architecture.largest_tables`
```sql
SELECT table_schema, table_name, engine, table_rows, data_length + index_length AS total_bytes, data_free FROM information_schema.tables WHERE table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY total_bytes DESC LIMIT 25
```
| table_schema | table_name | engine | table_rows | total_bytes | data_free |
| --- | --- | --- | --- | --- | --- |
| glpi | glpi_tickets | InnoDB | 2 | 540672 | 0 |
| glpi | glpi_users | InnoDB | 8 | 409600 | 0 |
| glpi | glpi_softwarelicenses | InnoDB | 0 | 393216 | 0 |
| glpi | glpi_printers | InnoDB | 0 | 393216 | 0 |
| glpi | glpi_projects | InnoDB | 0 | 376832 | 0 |
| glpi | glpi_networkequipments | InnoDB | 0 | 360448 | 0 |
| glpi | glpi_phones | InnoDB | 0 | 360448 | 0 |
| glpi | glpi_peripherals | InnoDB | 0 | 344064 | 0 |
| glpi | glpi_itemtranslations_itemtranslations | InnoDB | 881 | 344064 | 0 |
| glpi | glpi_monitors | InnoDB | 0 | 344064 | 0 |
| glpi | glpi_cables | InnoDB | 0 | 344064 | 0 |
| glpi | glpi_projecttasks | InnoDB | 0 | 344064 | 0 |
| glpi | glpi_computers | InnoDB | 2 | 344064 | 0 |
| glpi | glpi_changes | InnoDB | 0 | 344064 | 0 |
| glpi | glpi_itilcategories | InnoDB | 0 | 327680 | 0 |
| glpi | glpi_problems | InnoDB | 0 | 327680 | 0 |
| glpi | glpi_databaseinstances | InnoDB | 0 | 311296 | 0 |
| glpi | glpi_assets_assets | InnoDB | 0 | 311296 | 0 |
| glpi | glpi_unmanageds | InnoDB | 0 | 311296 | 0 |
| glpi | glpi_groups | InnoDB | 0 | 294912 | 0 |
| glpi | glpi_appliances | InnoDB | 0 | 294912 | 0 |
| glpi | glpi_tickettasks | InnoDB | 0 | 294912 | 0 |
| glpi | glpi_projecttasktemplates | InnoDB | 0 | 278528 | 0 |
| glpi | glpi_problemtasks | InnoDB | 0 | 262144 | 0 |
| glpi | glpi_racks | InnoDB | 0 | 262144 | 0 |

#### `architecture.server_id`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| read_only | OFF |
| server_id | 1 |

### High availability and disaster recovery
#### `ha_dr.binlog`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| binlog_expire_logs_seconds | 864000 |
| binlog_format | MIXED |
| expire_logs_days | 10.000000 |
| gtid_strict_mode | OFF |
| innodb_flush_log_at_trx_commit | 1 |
| log_bin | OFF |
| log_slave_updates | OFF |
| sync_binlog | 0 |

#### `ha_dr.replica_status`
```sql
SHOW REPLICA STATUS
```
_no rows_

#### `ha_dr.replicas_connected`
```sql
SELECT COUNT(*) AS replicas FROM information_schema.processlist WHERE command IN ('Binlog Dump','Binlog Dump GTID')
```
| replicas |
| --- |
| 0 |

### Database change management and release processes
#### `change_management.migration_tables`
```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name IN ('flyway_schema_history','schema_migrations','alembic_version','django_migrations','databasechangelog','knex_migrations','__EFMigrationsHistory','_prisma_migrations','goose_db_version','phinxlog')
```
_no rows_

#### `change_management.ddl_logging`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| general_log | OFF |
| log_output | FILE |

### Security configuration and encryption
#### `security.ssl`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| have_ssl | DISABLED |
| require_secure_transport | OFF |
| ssl_ca |  |
| ssl_cert |  |
| ssl_key |  |
| tls_version | TLSv1.2,TLSv1.3 |

#### `security.auth_plugins`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
_no rows_

#### `security.local_infile`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| local_infile | ON |
| secure_file_priv |  |
| skip_name_resolve | OFF |

### User access and authentication
#### `access.users`
```sql
SELECT User AS user, Host AS host, CASE WHEN JSON_EXTRACT(Priv, '$.auth_or[*].plugin') LIKE '%unix_socket%' THEN 'unix_socket' ELSE COALESCE(JSON_VALUE(Priv, '$.plugin'), 'mysql_native_password') END AS plugin, IF(JSON_EXTRACT(Priv, '$.account_locked') = true, 'Y', 'N') AS account_locked, IF(COALESCE(JSON_VALUE(Priv, '$.authentication_string'), '') = '' AND JSON_EXTRACT(Priv, '$.auth_or') IS NULL AND COALESCE(JSON_VALUE(Priv, '$.plugin'), 'mysql_native_password') NOT IN ('unix_socket','auth_socket'), 1, 0) AS empty_password, FROM_UNIXTIME(JSON_VALUE(Priv, '$.password_last_changed')) AS password_last_changed FROM mysql.global_priv ORDER BY User, Host
```
| user | host | plugin | account_locked | empty_password | password_last_changed |
| --- | --- | --- | --- | --- | --- |
| app | % | mysql_native_password | N | 0 | 2026-09-06 04:27:32 |
| discovery | localhost | mysql_native_password | N | 0 | 2026-09-06 04:27:32 |
| glpi | localhost | mysql_native_password | N | 0 | 2026-08-30 14:07:28 |
| mariadb.sys | localhost | mysql_native_password | Y | 1 | 1970-01-01 00:00:00 |
| mysql | localhost | unix_socket | N | 0 |  |
| root | localhost | unix_socket | N | 0 |  |

#### `access.global_privileges`
```sql
SELECT grantee, GROUP_CONCAT(privilege_type ORDER BY privilege_type) AS privileges, MAX(is_grantable) AS grantable FROM information_schema.user_privileges GROUP BY grantee
```
| grantee | privileges | grantable |
| --- | --- | --- |
| 'app'@'%' | USAGE | NO |
| 'discovery'@'localhost' | BINLOG MONITOR,PROCESS,SELECT,SHOW DATABASES,SLAVE MONITOR | NO |
| 'glpi'@'localhost' | USAGE | NO |
| 'mariadb.sys'@'localhost' | USAGE | NO |
| 'mysql'@'localhost' | ALTER,ALTER ROUTINE,BINLOG ADMIN,BINLOG MONITOR,BINLOG REPLAY,CONNECTION ADMIN,CREATE,CREATE ROUTINE,CREATE TABLESPACE,CREATE TEMPORARY TABLES,CREATE USER,CREA… | YES |
| 'root'@'localhost' | ALTER,ALTER ROUTINE,BINLOG ADMIN,BINLOG MONITOR,BINLOG REPLAY,CONNECTION ADMIN,CREATE,CREATE ROUTINE,CREATE TABLESPACE,CREATE TEMPORARY TABLES,CREATE USER,CREA… | YES |

#### `access.password_lifetime`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| default_password_lifetime | 0 |
| disconnect_on_expired_password | OFF |

### Backup and retention policies
#### `backup.binlog_retention`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| binlog_expire_logs_seconds | 864000 |
| binlog_format | MIXED |
| expire_logs_days | 10.000000 |
| gtid_strict_mode | OFF |
| innodb_flush_log_at_trx_commit | 1 |
| log_bin | OFF |
| log_slave_updates | OFF |
| sync_binlog | 0 |

#### `backup.backup_tooling_note`
| note |
| --- |
| Backups (mysqldump, mariabackup, xtrabackup, cloud snapshots), retention and restore tests live outside the server; request the schedule, retention policy and … |

### Cloud cost and resource usage
#### `cost.buffer_pool_vs_data`
```sql
SELECT @@innodb_buffer_pool_size AS buffer_pool_bytes, (SELECT SUM(data_length + index_length) FROM information_schema.tables WHERE engine = 'InnoDB') AS innodb_data_bytes
```
| buffer_pool_bytes | innodb_data_bytes |
| --- | --- |
| 134217728 | 51494912.0 |

#### `cost.fragmentation`
```sql
SELECT table_schema, table_name, data_free, data_length + index_length AS total_bytes FROM information_schema.tables WHERE data_free > 50*1024*1024 AND table_schema NOT IN ('mysql','information_schema','performance_schema','sys') ORDER BY data_free DESC LIMIT 25
```
_no rows_

#### `cost.connections_vs_max`
```sql
SELECT (SELECT COUNT(*) FROM information_schema.processlist) AS current_connections, @@max_connections AS max_connections
```
| current_connections | max_connections |
| --- | --- |
| 1 | 151 |

#### `cost.status_counters`
```sql
SHOW GLOBAL STATUS WHERE Variable_name IN ('Max_used_connections','Aborted_connects','Created_tmp_disk_tables','Innodb_buffer_pool_wait_free','Slow_queries','Threads_connected')
```
| Variable_name | Value |
| --- | --- |
| Aborted_connects | 1 |
| Created_tmp_disk_tables | 216 |
| Innodb_buffer_pool_wait_free | 0 |
| Max_used_connections | 1 |
| Slow_queries | 0 |
| Threads_connected | 1 |

### Monitoring and observability
#### `monitoring.settings`
```sql
SHOW GLOBAL VARIABLES (filtered)
```
| Variable_name | Value |
| --- | --- |
| innodb_monitor_enable |  |
| log_error |  |
| log_queries_not_using_indexes | OFF |
| log_warnings | 2 |
| long_query_time | 10.000000 |
| performance_schema | OFF |
| slow_query_log | OFF |

### Outstanding database concerns and operational issues
#### `operations.long_running`
```sql
SELECT id, user, host, db, command, time, state, LEFT(info, 120) AS query FROM information_schema.processlist WHERE command NOT IN ('Sleep','Binlog Dump','Binlog Dump GTID') AND time > 300 ORDER BY time DESC LIMIT 20
```
_no rows_

#### `operations.lock_waits`
```sql
SELECT COUNT(*) AS waiting FROM information_schema.innodb_lock_waits
```
| waiting |
| --- |
| 0 |

#### `operations.tables_without_pk`
```sql
SELECT t.table_schema, t.table_name, t.engine FROM information_schema.tables t WHERE t.table_type = 'BASE TABLE' AND t.table_schema NOT IN ('mysql','information_schema','performance_schema','sys') AND NOT EXISTS (SELECT 1 FROM information_schema.statistics s WHERE s.table_schema = t.table_schema AND s.table_name = t.table_name AND s.index_name = 'PRIMARY') ORDER BY 1,2 LIMIT 50
```
_no rows_

#### `operations.myisam_tables`
```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE engine = 'MyISAM' AND table_schema NOT IN ('mysql','information_schema','performance_schema','sys') LIMIT 50
```
| table_schema | table_name |
| --- | --- |
| shopdemo | legacy_log |

