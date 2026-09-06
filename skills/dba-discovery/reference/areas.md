# The ten review areas

For each area: the questions the page must answer, the evidence keys that answer them (PostgreSQL first, then MySQL or MariaDB), what good looks like, and the thresholds the rules in `discovery/rules.py` apply. Evidence keys are the headings in the appendix of the wiki page.

## 1. Database and platform inventory

Questions: which engine and exact version; is the line still supported and until when; which databases or schemas exist and how large; which extensions or plugins; the core settings that shape everything else (listen address, port, max connections, memory sizes, encoding, time zone).

Evidence: `inventory.version`, `inventory.databases`, `inventory.extensions`, `inventory.core_settings` (PostgreSQL); `inventory.version`, `inventory.uptime`, `inventory.databases`, `inventory.engines`, `inventory.core_settings` (MySQL).

Good: a supported line with more than a year left; sizes that match the owner's expectation; extensions the owner can name a purpose for.

Rules: past end of support is High; less than twelve months left is Medium; a line missing from the lifecycle table is an unknown.

## 2. Architecture and data flow

Questions: is this a primary or a standby; which applications connect, with which accounts, how many sessions each; what are the largest tables; is logical replication in play; are there foreign servers or linked data sources.

Evidence: `architecture.role`, `architecture.connections`, `architecture.largest_tables`, `architecture.logical_replication`, `architecture.foreign_servers` (PostgreSQL); `architecture.connections`, `architecture.largest_tables`, `architecture.server_id` (MySQL, where `read_only` and `super_read_only` tell primary from replica).

Good: every application has its own account and an `application_name`; the top tables are known to the owner; no unexplained foreign links.

Rules: no automatic findings; this area is read by a person. Note shared accounts, unknown applications and unexpected foreign servers as manual findings.

## 3. High availability and disaster recovery

Questions: is there a replica; how far behind; synchronous or asynchronous; are replication slots healthy; can WAL or binlog support replication at all; what is the failover procedure and when was it last exercised (interview).

Evidence: `ha_dr.replication`, `ha_dr.settings`, `ha_dr.archiver`, `ha_dr.slots` (PostgreSQL); `ha_dr.binlog`, `ha_dr.replica_status`, `ha_dr.replicas_connected` (MySQL).

Good: at least one streaming replica in state `streaming` with lag near zero; `wal_level` replica or logical; slots active; on MySQL `log_bin` ON with `binlog_format` ROW, `sync_binlog` 1 and `innodb_flush_log_at_trx_commit` 1 on the primary; a documented, rehearsed promotion.

Rules: no replica on a primary is High; `wal_level` minimal is High; replica not streaming is Medium; inactive slot retaining WAL is Medium; asynchronous replication is Low (a decision, not a defect); MySQL `log_bin` OFF is High; replication threads stopped is High; lag over 60 seconds is Medium; `sync_binlog` not 1 or flush at commit not 1 is Medium.

## 4. Database change management and release processes

Questions: how does a schema change reach production; is there a migration tool with a history table; is DDL logged; who can run DDL; is there a review step (interview).

Evidence: `change_management.migration_tables`, `change_management.ddl_logging`, `change_management.event_triggers` (PostgreSQL); `change_management.migration_tables`, `change_management.ddl_logging` (MySQL).

Good: one migration tool, its history table present, `log_statement` ddl on PostgreSQL, DDL rights limited to the deployment account.

Rules: no migration history table is Medium; PostgreSQL with `log_statement` none and no event triggers is Low.

## 5. Security configuration and encryption

Questions: is transport encrypted and required; how are passwords hashed; which networks may connect and with which method; are risky features on (local infile, name resolution).

Evidence: `security.ssl`, `security.hba`, `security.ssl_connections` (PostgreSQL); `security.ssl`, `security.auth_plugins`, `security.local_infile` (MySQL).

Good: TLS on and required for every network client; `scram-sha-256` (PostgreSQL) or `caching_sha2_password` (MySQL 8); `pg_hba` rows scoped to application subnets; `local_infile` OFF; `skip_name_resolve` ON.

Rules: TLS off with network listening is High; trust rules for host connections are High; any address rule is Medium; md5 hashing is Medium; MySQL `have_ssl` not YES is High; TLS available but not required is Medium; `local_infile` ON is Medium; `skip_name_resolve` OFF is Low.

## 6. User access and authentication

Questions: who is superuser or root; which accounts can log in from anywhere; which never expire; are there anonymous or passwordless accounts; can everyone create in `public`.

Evidence: `access.roles`, `access.public_schema`, `access.db_acl` (PostgreSQL); `access.users`, `access.global_privileges`, `access.password_lifetime` (MySQL).

Good: one break glass superuser with a vaulted password; people have personal accounts; services have scoped accounts limited by host or network; `public` schema without CREATE for PUBLIC.

Rules: extra superusers are Medium; PUBLIC CREATE on `public` is Medium; login roles without expiry are Low; BYPASSRLS is Low; anonymous accounts, empty passwords and root from any host are High; accounts from any host are Medium; SUPER on non system accounts is Medium; password lifetime 0 is Low.

## 7. Backup and retention policies

Questions: is point in time recovery possible (archiving or binlog); is archiving succeeding; what is the backup tool, schedule and retention; when was the last restore tested and how long did it take (interview).

Evidence: `backup.settings`, `backup.archiver`, `backup.backup_tooling_note` (PostgreSQL); `backup.binlog_retention`, `backup.backup_tooling_note` (MySQL); `interview.backup`.

Good: archiving on and succeeding (or binlog on with expiry set), a backup tool with off host copies, retention agreed with the business, a restore test in the last quarter with a measured duration.

Rules: `archive_mode` off is High; archiving failing is High; binlog never purged is Medium; the schedule and restore test are always an unknown until the owner answers.

## 8. Cloud cost and resource usage

Questions: what the platform costs per month and which line grows (interview and the cloud billing export, quoted as `interview.cost`); is memory sized to the working set; are there indexes nobody uses; are tables bloated; is connection headroom adequate; is the instance class larger than the measured load needs.

Evidence: `cost.cache_hit`, `cost.unused_indexes`, `cost.dead_tuples`, `cost.connections_vs_max` (PostgreSQL); `cost.buffer_pool_vs_data`, `cost.fragmentation`, `cost.connections_vs_max`, `cost.status_counters` (MySQL); `interview.cost`.

Good: cache hit above 95 percent on a long statistics window; no unused indexes on hot tables; dead rows under 10 percent; connections under half of the maximum with a pooler in front.

Rules: cache hit under 90 percent with meaningful reads is Medium; deadlocks recorded is Low; unused indexes is Low; over 20 percent dead rows on a table with more than 10,000 dead rows is Medium; connections over 80 percent of maximum is High; `max_connections` over 500 without a pooler is Low; buffer pool much smaller than InnoDB data is Medium; fragmentation over 50 MB per table is Low; buffer pool wait free above zero is Medium.

## 9. Monitoring and observability

Questions: can a slow statement be found after the fact; is per statement statistics available; is timing instrumentation on; where do logs go and who reads them (interview).

Evidence: `monitoring.settings`, `monitoring.pg_stat_statements` (PostgreSQL); `monitoring.settings` (MySQL); `interview.monitoring`.

Good: `pg_stat_statements` installed, `log_min_duration_statement` around 1 second, `track_io_timing`, `log_checkpoints` and `log_lock_waits` on, logs collected and rotated; on MySQL `slow_query_log` ON with `long_query_time` near 1 and `performance_schema` ON.

Rules: `autovacuum` off is High; no `pg_stat_statements` is Medium; slow statements not logged is Medium; each timing setting off is Low; slow query log OFF is Medium; Performance Schema OFF is Low.

## 10. Outstanding database concerns and operational issues

Questions: is transaction id age under control; are there invalid indexes; which tables lack a primary key; are legacy storage engines in use; what is running long right now; are sessions waiting on locks.

Evidence: `operations.wraparound`, `operations.invalid_indexes`, `operations.tables_without_pk`, `operations.long_running`, `operations.lock_waits` (PostgreSQL); `operations.myisam_tables`, `operations.tables_without_pk`, `operations.long_running`, `operations.lock_waits` (MySQL).

Good: transaction id age under 50 percent of the freeze limit; no invalid indexes; every table has a primary key; InnoDB only; long statements known to the owner.

Rules: age over 80 percent of the freeze limit is High, over 50 percent is Medium; invalid indexes are Medium; tables without a primary key are Low (Medium on MySQL with row based binlog); MyISAM in application schemas is Medium; statements over five minutes at collection time are Low.
