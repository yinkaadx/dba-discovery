-- Platform inventory for database discovery runs (SQLite dialect; also valid on PostgreSQL after replacing AUTOINCREMENT with GENERATED ALWAYS AS IDENTITY).
-- One row per platform (engine, host, port); databases and runs hang off it; findings and unknowns hang off runs.

CREATE TABLE IF NOT EXISTS platforms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    engine        TEXT NOT NULL,                 -- postgres | mysql
    flavour       TEXT NOT NULL,                 -- PostgreSQL | MySQL | MariaDB
    version       TEXT NOT NULL,
    host          TEXT NOT NULL,
    port          INTEGER NOT NULL,
    environment   TEXT,                          -- production | staging | development, from the run command
    owner         TEXT,                          -- team or person accountable, from the run command
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    UNIQUE (engine, host, port)
);

CREATE TABLE IF NOT EXISTS databases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id   INTEGER NOT NULL REFERENCES platforms(id),
    name          TEXT NOT NULL,
    size_bytes    INTEGER,
    last_seen     TEXT NOT NULL,
    UNIQUE (platform_id, name)
);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id   INTEGER NOT NULL REFERENCES platforms(id),
    run_name      TEXT NOT NULL UNIQUE,
    collected_at  TEXT NOT NULL,
    collector_user TEXT,
    evidence_path TEXT,
    report_path   TEXT,
    high          INTEGER NOT NULL DEFAULT 0,
    medium        INTEGER NOT NULL DEFAULT 0,
    low           INTEGER NOT NULL DEFAULT 0,
    info          INTEGER NOT NULL DEFAULT 0,
    unknowns      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES discovery_runs(id),
    code          TEXT NOT NULL,                 -- PG-SEC-001 style id, unique inside a run
    area          TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('High','Medium','Low','Info')),
    title         TEXT NOT NULL,
    detail        TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    effort        TEXT NOT NULL CHECK (effort IN ('Small','Medium','Large')),
    evidence_keys TEXT NOT NULL,                 -- comma separated evidence keys into the run's evidence.json
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','accepted','in_progress','done','risk_accepted')),
    owner         TEXT,
    due           TEXT,
    UNIQUE (run_id, code)
);

CREATE TABLE IF NOT EXISTS unknowns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES discovery_runs(id),
    area          TEXT NOT NULL,
    question      TEXT NOT NULL,
    how_to_obtain TEXT NOT NULL,
    resolved      INTEGER NOT NULL DEFAULT 0
);

-- Latest run per platform.
CREATE VIEW IF NOT EXISTS v_latest_runs AS
SELECT r.*
FROM discovery_runs r
JOIN (SELECT platform_id, MAX(collected_at) AS collected_at FROM discovery_runs GROUP BY platform_id) l
  ON l.platform_id = r.platform_id AND l.collected_at = r.collected_at;

-- One line per platform with the open finding counts from its latest run.
CREATE VIEW IF NOT EXISTS v_platform_summary AS
SELECT p.id, p.engine, p.flavour, p.version, p.host, p.port, p.environment, p.owner, p.last_seen,
       (SELECT COUNT(*) FROM databases d WHERE d.platform_id = p.id) AS databases,
       (SELECT COALESCE(SUM(size_bytes), 0) FROM databases d WHERE d.platform_id = p.id) AS size_bytes,
       r.run_name AS latest_run, r.collected_at AS latest_collected_at,
       (SELECT COUNT(*) FROM findings f WHERE f.run_id = r.id AND f.status NOT IN ('done','risk_accepted') AND f.severity = 'High')   AS open_high,
       (SELECT COUNT(*) FROM findings f WHERE f.run_id = r.id AND f.status NOT IN ('done','risk_accepted') AND f.severity = 'Medium') AS open_medium,
       (SELECT COUNT(*) FROM findings f WHERE f.run_id = r.id AND f.status NOT IN ('done','risk_accepted') AND f.severity = 'Low')    AS open_low,
       (SELECT COUNT(*) FROM unknowns u WHERE u.run_id = r.id AND u.resolved = 0) AS open_unknowns
FROM platforms p
LEFT JOIN v_latest_runs r ON r.platform_id = p.id;

-- Open findings across every platform, highest severity first.
CREATE VIEW IF NOT EXISTS v_open_findings AS
SELECT p.flavour, p.host, p.port, p.environment, r.run_name, f.code, f.area, f.severity, f.effort, f.title, f.recommendation, f.status, f.owner, f.due
FROM findings f
JOIN v_latest_runs r ON r.id = f.run_id
JOIN platforms p ON p.id = r.platform_id
WHERE f.status NOT IN ('done','risk_accepted')
ORDER BY CASE f.severity WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 WHEN 'Low' THEN 2 ELSE 3 END,
         CASE f.effort WHEN 'Small' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, p.host, f.code;
