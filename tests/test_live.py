"""End to end against real servers when DSNs are provided; skipped otherwise.

  DISCOVERY_PG_DSN=postgresql://discovery:pw@127.0.0.1:5432/importer_demo
  DISCOVERY_MYSQL_DSN=mysql://discovery:pw@127.0.0.1:3306/shopdemo
"""
from __future__ import annotations

import os

import pytest

from discovery.cli import main


@pytest.mark.skipif(not os.environ.get("DISCOVERY_PG_DSN"), reason="DISCOVERY_PG_DSN not set")
def test_postgres_end_to_end(tmp_path):
    assert main(["run", "--engine", "postgres", "--dsn", os.environ["DISCOVERY_PG_DSN"], "--name", "live-pg", "--out", str(tmp_path)]) == 0
    md = (tmp_path / "live-pg" / "wiki.md").read_text(encoding="utf-8")
    assert "# Database discovery: PostgreSQL" in md and "## Appendix A: Evidence" in md
    assert "password" not in md.lower().split("## appendix a")[0].split("run `")[0]  # the DSN never reaches the page


@pytest.mark.skipif(not os.environ.get("DISCOVERY_MYSQL_DSN"), reason="DISCOVERY_MYSQL_DSN not set")
def test_mysql_end_to_end(tmp_path):
    assert main(["run", "--engine", "mysql", "--dsn", os.environ["DISCOVERY_MYSQL_DSN"], "--name", "live-my", "--out", str(tmp_path)]) == 0
    md = (tmp_path / "live-my" / "wiki.md").read_text(encoding="utf-8")
    assert "# Database discovery: MySQL or MariaDB" in md and "SHOW GLOBAL VARIABLES" in md
