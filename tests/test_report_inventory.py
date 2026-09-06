"""The wiki page renders every section, cites evidence, and the inventory store round trips a run."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from discovery import inventory as inv
from discovery.report import prioritized, render
from discovery.rules import assess_postgres
from tests.test_rules import TODAY, healthy_pg, ok, pg_settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_run(tmp_path, name="pg-test"):
    ev = healthy_pg()
    ev["ha_dr"]["replication"] = ok([])
    ev["backup"]["settings"] = pg_settings(archive_mode="off")
    ev["inventory"]["databases"] = ok([{"datname": "app", "size_bytes": 1024 ** 3, "size": "1024 MB"}])
    ev["inventory"]["extensions"] = ok([{"extname": "plpgsql", "extversion": "1.0"}])
    ctx = assess_postgres(ev, TODAY)
    findings = [f.as_dict() for f in ctx.findings]
    unknowns = [u.as_dict() for u in ctx.unknowns]
    md = render("postgres", "db1:5432", name, "2026-09-06 10:00 UTC", "discovery", ev, findings, unknowns)
    run_dir = tmp_path / name
    run_dir.mkdir()
    (run_dir / "wiki.md").write_text(md, encoding="utf-8")
    (run_dir / "evidence.json").write_text(json.dumps(ev), encoding="utf-8")
    (run_dir / "findings.json").write_text(json.dumps({"findings": findings, "unknowns": unknowns}), encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps({"run_name": name, "engine": "postgres", "collected_at": "2026-09-06 10:00 UTC", "collector_user": "discovery", "target": "db1:5432",
                                                  "environment": "production", "owner": "data team",
                                                  "platform": {"engine": "postgres", "flavour": "PostgreSQL", "version": "16.4", "host": "db1", "port": 5432, "databases": [{"name": "app", "size_bytes": 1024 ** 3}]}}), encoding="utf-8")
    return run_dir, md, findings, unknowns


def test_wiki_structure_and_citations(tmp_path):
    run_dir, md, findings, unknowns = make_run(tmp_path)
    for heading in ("## 1. Summary", "### Top actions", "## 2. Findings by area", "## 3. Unknowns and how to obtain them", "## 4. Prioritized recommendations", "## Appendix A: Evidence"):
        assert heading in md
    for n, title in enumerate(["Database and platform inventory", "Architecture and data flow", "High availability and disaster recovery",
                               "Database change management and release processes", "Security configuration and encryption", "User access and authentication",
                               "Backup and retention policies", "Cloud cost and resource usage", "Monitoring and observability",
                               "Outstanding database concerns and operational issues"], 1):
        assert f"### 2.{n} {title}" in md
    for f in findings:
        assert f"`{f['id']}`" in md
        for e in f["evidence"]:
            assert f"#### `{e}`" in md, e  # every cited key has an appendix block
    assert "Backup schedule, retention" in md
    assert "```sql" in md
    ranked = prioritized(findings)
    assert [f["severity"] for f in ranked] == sorted([f["severity"] for f in ranked], key=lambda s: {"High": 0, "Medium": 1, "Low": 2, "Info": 3}[s])


def test_wiki_prose_has_no_dashes():
    ev = healthy_pg()
    ev["ha_dr"]["replication"] = ok([])
    ev["security"]["ssl"] = pg_settings(ssl="off", password_encryption="md5", listen_addresses="*")
    ctx = assess_postgres(ev, TODAY)
    for f in ctx.findings:
        for text in (f.title, f.detail, f.recommendation):
            assert "—" not in text and "–" not in text, f.id
            stripped = re.sub(r"`[^`]*`", "", text)  # code spans may carry hyphens (scram-sha-256, pt-query-digest)
            assert not re.search(r"[A-Za-z]-[A-Za-z]", stripped), (f.id, text)


def test_inventory_round_trip(tmp_path):
    run_dir, md, findings, unknowns = make_run(tmp_path)
    store = tmp_path / "inv.sqlite"
    conn = inv.connect(str(store))
    r = inv.load_run(conn, str(run_dir))
    assert r["findings"] == len(findings) and r["High"] == 2
    r2 = inv.load_run(conn, str(run_dir))  # reload is idempotent
    assert conn.execute("SELECT COUNT(*) FROM discovery_runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == len(findings)
    plats = inv.platforms(conn)
    assert len(plats) == 1 and plats[0]["open_high"] == 2 and plats[0]["databases"] == 1 and plats[0]["environment"] == "production"
    high = inv.open_findings(conn, "High")
    assert {f["code"] for f in high} == {"PG-HA-001", "PG-BKP-001"}
    assert inv.set_status(conn, "pg-test", "PG-BKP-001", "done") == 1
    assert {f["code"] for f in inv.open_findings(conn, "High")} == {"PG-HA-001"}
    assert inv.platforms(conn)[0]["open_high"] == 1
    out = tmp_path / "platforms.csv"
    assert inv.export_csv(conn, str(out)) == 1 and "PostgreSQL" in out.read_text()


def test_cli_assess_and_inventory(tmp_path):
    run_dir, md, findings, unknowns = make_run(tmp_path, "cli-run")
    env = {**os.environ, "PYTHONPATH": ROOT}
    r = subprocess.run([sys.executable, "-m", "discovery", "assess", "--run", str(run_dir)], capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0 and "re assessed cli-run" in r.stdout, r.stderr
    store = tmp_path / "inv.sqlite"
    r = subprocess.run([sys.executable, "-m", "discovery", "inventory", "load", "--store", str(store), "--run", str(run_dir)], capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0 and "loaded" in r.stdout, r.stderr
    r = subprocess.run([sys.executable, "-m", "discovery", "inventory", "list", "--store", str(store)], capture_output=True, text=True, env=env, cwd=ROOT)
    assert "PostgreSQL" in r.stdout and "cli-run" in r.stdout
