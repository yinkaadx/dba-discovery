"""Platform inventory store (SQLite). Loads discovery runs and answers the questions a manager asks:
which platforms exist, what version they run, what is open, and what changed since the last run."""
from __future__ import annotations

import csv
import json
import os
import sqlite3

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inventory", "schema.sql")


def connect(store: str) -> sqlite3.Connection:
    conn = sqlite3.connect(store)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    return conn


def load_run(conn: sqlite3.Connection, run_dir: str) -> dict:
    """Upsert the platform, refresh its databases, insert the run with its findings and unknowns. Idempotent per run name."""
    with open(os.path.join(run_dir, "run.json"), "r", encoding="utf-8") as fh:
        run = json.load(fh)
    with open(os.path.join(run_dir, "findings.json"), "r", encoding="utf-8") as fh:
        fj = json.load(fh)
    p = run["platform"]
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO platforms (engine, flavour, version, host, port, environment, owner, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (engine, host, port) DO UPDATE SET flavour = excluded.flavour, version = excluded.version,
             environment = COALESCE(excluded.environment, platforms.environment), owner = COALESCE(excluded.owner, platforms.owner), last_seen = excluded.last_seen""",
        (p["engine"], p["flavour"], p["version"], p["host"], p["port"], run.get("environment"), run.get("owner"), run["collected_at"], run["collected_at"]),
    )
    platform_id = cur.execute("SELECT id FROM platforms WHERE engine = ? AND host = ? AND port = ?", (p["engine"], p["host"], p["port"])).fetchone()[0]
    for d in p.get("databases", []):
        cur.execute(
            """INSERT INTO databases (platform_id, name, size_bytes, last_seen) VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, name) DO UPDATE SET size_bytes = excluded.size_bytes, last_seen = excluded.last_seen""",
            (platform_id, d["name"], d.get("size_bytes"), run["collected_at"]),
        )
    existing = cur.execute("SELECT id FROM discovery_runs WHERE run_name = ?", (run["run_name"],)).fetchone()
    if existing:
        run_id = existing[0]
        cur.execute("DELETE FROM findings WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM unknowns WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM discovery_runs WHERE id = ?", (run_id,))
    counts = {s: sum(1 for f in fj["findings"] if f["severity"] == s) for s in ("High", "Medium", "Low", "Info")}
    cur.execute(
        """INSERT INTO discovery_runs (platform_id, run_name, collected_at, collector_user, evidence_path, report_path, high, medium, low, info, unknowns)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (platform_id, run["run_name"], run["collected_at"], run.get("collector_user"), os.path.join(run_dir, "evidence.json"), os.path.join(run_dir, "wiki.md"),
         counts["High"], counts["Medium"], counts["Low"], counts["Info"], len(fj["unknowns"])),
    )
    run_id = cur.lastrowid
    for f in fj["findings"]:
        cur.execute(
            "INSERT INTO findings (run_id, code, area, severity, title, detail, recommendation, effort, evidence_keys) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, f["id"], f["area"], f["severity"], f["title"], f["detail"], f["recommendation"], f["effort"], ",".join(f["evidence"])),
        )
    for u in fj["unknowns"]:
        cur.execute("INSERT INTO unknowns (run_id, area, question, how_to_obtain) VALUES (?, ?, ?, ?)", (run_id, u["area"], u["question"], u["how_to_obtain"]))
    conn.commit()
    return {"platform_id": platform_id, "run_id": run_id, "findings": len(fj["findings"]), "unknowns": len(fj["unknowns"]), **counts}


def platforms(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM v_platform_summary ORDER BY flavour, host, port")]


def open_findings(conn: sqlite3.Connection, severity: str | None = None) -> list[dict]:
    sql = "SELECT * FROM v_open_findings"
    params: tuple = ()
    if severity:
        sql += " WHERE severity = ?"
        params = (severity,)
    return [dict(r) for r in conn.execute(sql, params)]


def set_status(conn: sqlite3.Connection, run_name: str, code: str, status: str, owner: str | None = None, due: str | None = None) -> int:
    cur = conn.execute(
        "UPDATE findings SET status = ?, owner = COALESCE(?, owner), due = COALESCE(?, due) WHERE code = ? AND run_id = (SELECT id FROM discovery_runs WHERE run_name = ?)",
        (status, owner, due, code, run_name),
    )
    conn.commit()
    return cur.rowcount


def export_csv(conn: sqlite3.Connection, out_path: str) -> int:
    rows = platforms(conn)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return len(rows)


def text_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "(no rows)"
    widths = {c: max(len(c), *(len(str(r.get(c, "") if r.get(c) is not None else "")) for r in rows)) for c in columns}
    line = "  ".join(c.ljust(widths[c]) for c in columns)
    out = [line, "  ".join("-" * widths[c] for c in columns)]
    for r in rows:
        out.append("  ".join(str(r.get(c, "") if r.get(c) is not None else "").ljust(widths[c]) for c in columns))
    return "\n".join(out)
