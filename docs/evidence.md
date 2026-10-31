# Evidence log

Everything below was captured on 6 September 2026 against a local PostgreSQL 16.13 and a local MariaDB 10.11.14, both queried with the least privilege discovery accounts from the reference files. Passwords are shown as PASSWORD, and the checkout folder as ~/dba-discovery.

## Tests

```
$ python -m pytest -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- python
cachedir: .pytest_cache
rootdir: ~/dba-discovery
configfile: pyproject.toml
testpaths: tests
collecting ... collected 20 items

tests/test_live.py::test_postgres_end_to_end PASSED                      [  5%]
tests/test_live.py::test_mysql_end_to_end PASSED                         [ 10%]
tests/test_report_inventory.py::test_wiki_structure_and_citations PASSED [ 15%]
tests/test_report_inventory.py::test_wiki_prose_has_no_dashes PASSED     [ 20%]
tests/test_report_inventory.py::test_inventory_round_trip PASSED         [ 25%]
tests/test_report_inventory.py::test_cli_assess_and_inventory PASSED     [ 30%]
tests/test_rules.py::test_healthy_postgres_raises_nothing PASSED         [ 35%]
tests/test_rules.py::test_postgres_single_instance_without_archiving PASSED [ 40%]
tests/test_rules.py::test_postgres_standby_is_not_reported_as_single_primary PASSED [ 45%]
tests/test_rules.py::test_postgres_end_of_life_version PASSED            [ 50%]
tests/test_rules.py::test_postgres_security_rules PASSED                 [ 55%]
tests/test_rules.py::test_postgres_missing_permission_becomes_unknown_not_finding PASSED [ 60%]
tests/test_rules.py::test_postgres_access_and_capacity_rules PASSED      [ 65%]
tests/test_rules.py::test_finding_ids_are_unique_and_sequential_per_area PASSED [ 70%]
tests/test_rules.py::test_healthy_mysql_raises_nothing PASSED            [ 75%]
tests/test_rules.py::test_mysql_end_of_life_lines PASSED                 [ 80%]
tests/test_rules.py::test_mysql_durability_and_replication_rules PASSED  [ 85%]
tests/test_rules.py::test_mysql_security_and_access_rules PASSED         [ 90%]
tests/test_rules.py::test_mysql_operations_rules_scale_with_replication_format PASSED [ 95%]
tests/test_rules.py::test_every_finding_carries_evidence_and_valid_labels PASSED [100%]

============================== 20 passed in 0.88s ==============================
```

## Command line session

```
$ python -m discovery run --engine postgres --dsn postgresql://discovery:PASSWORD@127.0.0.1:5432/importer_demo --name postgres-local --environment development --owner "Yinka"
run postgres-local: 36 of 36 evidence blocks collected, 12 findings (High 2, Medium 3, Low 6, Info 1), 1 unknowns
wrote runs/postgres-local/evidence.json, findings.json, run.json, wiki.md

$ python -m discovery run --engine mysql --dsn mysql://discovery:PASSWORD@127.0.0.1:3306/shopdemo --name mariadb-local --environment development --owner "Yinka"
run mariadb-local: 30 of 30 evidence blocks collected, 11 findings (High 3, Medium 5, Low 3, Info 0), 1 unknowns
wrote runs/mariadb-local/evidence.json, findings.json, run.json, wiki.md

$ mysql -u root -e "SET GLOBAL slow_query_log = ON; SET GLOBAL local_infile = OFF;"      (two fixes applied by the owner)
$ python -m discovery run --engine mysql --dsn mysql://discovery:PASSWORD@127.0.0.1:3306/shopdemo --name mariadb-local-after --environment development --owner "Yinka"
run mariadb-local-after: 30 of 30 evidence blocks collected, 9 findings (High 3, Medium 3, Low 3, Info 0), 1 unknowns
wrote runs/mariadb-local-after/evidence.json, findings.json, run.json, wiki.md

$ python -m discovery diff --a runs/mariadb-local --b runs/mariadb-local-after
comparing runs/mariadb-local (before) with runs/mariadb-local-after (after)
resolved 2, new 0, remaining 9
  resolved  MY-MON-001   Medium  Slow query log is off
  resolved  MY-SEC-002   Medium  local_infile is enabled
  remaining MY-OPS-001   Medium  1 MyISAM table(s) in application schemas
  remaining MY-ACC-001   Medium  Accounts accept connections from any host
  remaining MY-HA-001    High    Binary logging is off
  remaining MY-SEC-002   Low     Host name resolution is on for connections
  remaining MY-CHG-001   Medium  No schema migration history table found
  remaining MY-ACC-002   Low     Passwords never expire by default
  remaining MY-MON-001   Low     Performance Schema is off
  remaining MY-HA-002    High    Single server with no replica
  remaining MY-SEC-001   High    TLS is not available on the server

$ python -m discovery inventory load --run runs/postgres-local
loaded runs/postgres-local: platform 1, run 1, 12 findings (High 2, Medium 3, Low 6), 1 unknowns
$ python -m discovery inventory load --run runs/mariadb-local-after
loaded runs/mariadb-local-after: platform 2, run 2, 9 findings (High 3, Medium 3, Low 3), 1 unknowns

$ python -m discovery inventory list
flavour     version                                host       port  environment  owner  databases  size_bytes  latest_run           open_high  open_medium  open_low  open_unknowns
----------  -------------------------------------  ---------  ----  -----------  -----  ---------  ----------  -------------------  ---------  -----------  --------  -------------
MariaDB     10.11.14-MariaDB-0ubuntu0.24.04.1      127.0.0.1  3306  development  Yinka  2          48694272    mariadb-local-after  3          3            3         1            
PostgreSQL  16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)  127.0.0.1  5432  development  Yinka  3          24245317    postgres-local       2          3            6         1            

$ python -m discovery inventory findings --severity High
flavour     host       run_name             code        severity  effort  title                                     status  owner  due
----------  ---------  -------------------  ----------  --------  ------  ----------------------------------------  ------  -----  ---
MariaDB     127.0.0.1  mariadb-local-after  MY-HA-001   High      Small   Binary logging is off                     open              
MariaDB     127.0.0.1  mariadb-local-after  MY-SEC-001  High      Small   TLS is not available on the server        open              
PostgreSQL  127.0.0.1  postgres-local       PG-BKP-001  High      Medium  WAL archiving is off                      open              
MariaDB     127.0.0.1  mariadb-local-after  MY-HA-002   High      Large   Single server with no replica             open              
PostgreSQL  127.0.0.1  postgres-local       PG-HA-001   High      Large   Single primary with no streaming replica  open              

$ python -m discovery inventory status --run-name mariadb-local-after --code MY-SEC-001 --status in_progress --owner "platform team" --due 2026-09-20
updated 1 finding(s)
$ python -m discovery inventory findings --severity High
flavour     host       run_name             code        severity  effort  title                                     status       owner          due       
----------  ---------  -------------------  ----------  --------  ------  ----------------------------------------  -----------  -------------  ----------
MariaDB     127.0.0.1  mariadb-local-after  MY-HA-001   High      Small   Binary logging is off                     open                                  
MariaDB     127.0.0.1  mariadb-local-after  MY-SEC-001  High      Small   TLS is not available on the server        in_progress  platform team  2026-09-20
PostgreSQL  127.0.0.1  postgres-local       PG-BKP-001  High      Medium  WAL archiving is off                      open                                  
MariaDB     127.0.0.1  mariadb-local-after  MY-HA-002   High      Large   Single server with no replica             open                                  
PostgreSQL  127.0.0.1  postgres-local       PG-HA-001   High      Large   Single primary with no streaming replica  open                                  

$ python -m discovery inventory export --out inventory/platforms.csv
exported 2 platform(s) to inventory/platforms.csv
$ cat inventory/platforms.csv
id,engine,flavour,version,host,port,environment,owner,last_seen,databases,size_bytes,latest_run,latest_collected_at,open_high,open_medium,open_low,open_unknowns
2,mysql,MariaDB,10.11.14-MariaDB-0ubuntu0.24.04.1,127.0.0.1,3306,development,Yinka,2026-09-06 04:51 UTC,2,48694272,mariadb-local-after,2026-09-06 04:51 UTC,3,3,3,1
1,postgres,PostgreSQL,16.13 (Ubuntu 16.13-0ubuntu0.24.04.1),127.0.0.1,5432,development,Yinka,2026-09-06 04:51 UTC,3,24245317,postgres-local,2026-09-06 04:51 UTC,2,3,6,1
```

## Permission behaviour observed

PostgreSQL with `pg_monitor` only: 35 of 36 blocks collected; `security.hba` failed with `permission denied for function pg_hba_file_rules` and the page listed the unknown with the grant to run. After `GRANT EXECUTE ON FUNCTION pg_hba_file_rules() TO discovery` in that database: 36 of 36.

MariaDB without `REPLICA MONITOR`: 29 of 30 blocks collected; `ha_dr.replica_status` failed with error 1227 (`SUPER, SLAVE MONITOR privilege(s)`), the single server rule stayed silent and the page listed the unknown `Replica status of this server` with the grant to run. After the grant: 30 of 30 and the High finding `Single server with no replica` appeared.

MariaDB `information_schema.table_constraints` returned zero rows for the discovery user while root saw 598, so the primary key check reads `information_schema.statistics` instead; MariaDB `mysql.user` is a compatibility view without the lock flag, so the account list is read from `mysql.global_priv`, which correctly reports `mariadb.sys` as locked and `root` and `mysql` as socket authenticated.
