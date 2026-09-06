"""Render the discovery wiki page (Markdown) from evidence, findings and unknowns.

The page is written for two readers at once: a manager who reads the summary
and the prioritized table, and an engineer who wants the exact query behind
each statement, which is why every finding carries evidence keys that point
into the appendix.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
from typing import Any

from .collectors_pg import AREAS

AREA_TITLES = {
    "inventory": "Database and platform inventory", "architecture": "Architecture and data flow", "ha_dr": "High availability and disaster recovery",
    "change_management": "Database change management and release processes", "security": "Security configuration and encryption", "access": "User access and authentication",
    "backup": "Backup and retention policies", "cost": "Cloud cost and resource usage", "monitoring": "Monitoring and observability",
    "operations": "Outstanding database concerns and operational issues",
}
SEV_RANK = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
EFF_RANK = {"Small": 0, "Medium": 1, "Large": 2}


def jsonable(v: Any):
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x) for x in v]
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, dt.timedelta):
        return str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8", "replace")
    return v


def cell(v: Any, limit: int = 160) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        v = ", ".join(str(x) for x in v)
    s = str(v).replace("|", "\\|").replace("\n", " ").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(cell(x) for x in r) + " |")
    return "\n".join(out)


def rows_table(rows: list[dict], limit: int = 25) -> str:
    if not rows:
        return "_no rows_"
    cols = list(rows[0].keys())
    body = table(cols, [[r.get(c) for c in cols] for r in rows[:limit]])
    if len(rows) > limit:
        body += f"\n\n_{len(rows) - limit} more row(s) in the JSON evidence file_"
    return body


def prioritized(findings: list[dict]) -> list[dict]:
    return sorted(findings, key=lambda f: (SEV_RANK.get(f["severity"], 9), EFF_RANK.get(f["effort"], 9), f["id"]))


def _pg_summary(ev: dict) -> list[list[str]]:
    rows = []
    v = ev["inventory"].get("version", {}).get("rows") or [{}]
    rows.append(["Version", v[0].get("version", "unknown")])
    rows.append(["Started", f"{v[0].get('started_at', 'unknown')} (uptime {v[0].get('uptime', 'unknown')})"])
    role = ev["architecture"].get("role", {}).get("rows") or [{}]
    rows.append(["Role", "standby (in recovery)" if role[0].get("in_recovery") else "primary"])
    dbs = ev["inventory"].get("databases", {}).get("rows") or []
    total = sum(int(d.get("size_bytes") or 0) for d in dbs)
    rows.append(["Databases", f"{len(dbs)} ({', '.join(d['datname'] + ' ' + str(d.get('size')) for d in dbs[:8])}); total {total / 1024 ** 2:.0f} MB"])
    ext = ev["inventory"].get("extensions", {}).get("rows") or []
    rows.append(["Extensions", ", ".join(e["extname"] + " " + str(e["extversion"]) for e in ext) or "none"])
    cvm = ev["cost"].get("connections_vs_max", {}).get("rows") or [{}]
    rows.append(["Connections", f"{cvm[0].get('current_connections', '?')} of max_connections {cvm[0].get('max_connections', '?')}"])
    rep = ev["ha_dr"].get("replication", {})
    rows.append(["Streaming replicas", str(len(rep.get("rows", []))) if rep.get("ok") else "unknown (" + rep.get("error", "not collected")[:60] + ")"])
    return rows


def _mysql_summary(ev: dict) -> list[list[str]]:
    rows = []
    v = ev["inventory"].get("version", {}).get("rows") or [{}]
    rows.append(["Version", f"{v[0].get('version', 'unknown')} ({v[0].get('flavour', '')}) on {v[0].get('host', '?')}:{v[0].get('port', '?')}"])
    up = ev["inventory"].get("uptime", {}).get("rows") or [{}]
    secs = int(up[0].get("Value") or 0)
    rows.append(["Uptime", f"{secs // 86400} d {(secs % 86400) // 3600} h"])
    dbs = ev["inventory"].get("databases", {}).get("rows") or []
    total = sum(int(d.get("size_bytes") or 0) for d in dbs)
    rows.append(["Schemas", f"{len(dbs)} ({', '.join(d['db'] + ' ' + str(d.get('tables')) + ' tables' for d in dbs[:8])}); data {total / 1024 ** 2:.0f} MB"])
    eng = ev["inventory"].get("engines", {}).get("rows") or []
    rows.append(["Storage engines", ", ".join(f"{e['engine']} {e['tables']}" for e in eng) or "none"])
    cvm = ev["cost"].get("connections_vs_max", {}).get("rows") or [{}]
    rows.append(["Connections", f"{cvm[0].get('current_connections', '?')} of max_connections {cvm[0].get('max_connections', '?')}"])
    rep = ev["ha_dr"].get("replicas_connected", {}).get("rows") or [{}]
    rows.append(["Replicas connected", str(rep[0].get("replicas", "unknown"))])
    return rows


def render(engine: str, target: str, run_name: str, collected_at: str, collector_user: str, ev: dict, findings: list[dict], unknowns: list[dict]) -> str:
    label = "PostgreSQL" if engine == "postgres" else "MySQL or MariaDB"
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_RANK}
    by_area = {a: [f for f in findings if f["area"] == a] for a in AREAS}
    ranked = prioritized(findings)
    md = []
    md.append(f"# Database discovery: {label} at {target}")
    md.append(f"Run `{run_name}`, evidence collected {collected_at} with the read only account `{collector_user}`. Every statement below cites an evidence key; the appendix holds the query and the rows returned so anyone can rerun it.")
    md.append("")
    md.append("## 1. Summary")
    md.append(table(["Item", "Value"], (_pg_summary if engine == "postgres" else _mysql_summary)(ev)))
    md.append("")
    md.append(table(["Severity", "Findings"], [[s, counts[s]] for s in SEV_RANK] + [["Unknowns", len(unknowns)]]))
    md.append("")
    md.append("### Top actions")
    if ranked:
        for i, f in enumerate(ranked[:5], 1):
            md.append(f"{i}. **{f['title']}** ({f['severity']}, {f['effort'].lower()} effort): {f['recommendation']}")
    else:
        md.append("No finding was raised from the evidence collected.")
    md.append("")
    md.append("## 2. Findings by area")
    for n, area in enumerate(AREAS, 1):
        md.append(f"### 2.{n} {AREA_TITLES[area]}")
        keys = list(ev.get(area, {}).keys())
        md.append("Evidence reviewed: " + ", ".join(f"`{area}.{k}`" for k in keys) + ".")
        md.append("")
        fs = by_area[area]
        if fs:
            for f in fs:
                md.append(f"**`{f['id']}` {f['title']}** ({f['severity']})  ")
                md.append(f"What the evidence shows: {f['detail']}  ")
                md.append(f"Recommendation: {f['recommendation']} Effort: {f['effort'].lower()}. Evidence: " + ", ".join(f"`{e}`" for e in f["evidence"]) + ".")
                md.append("")
        else:
            md.append("No finding in this area from the evidence collected.")
            md.append("")
        us = [u for u in unknowns if u["area"] == area]
        for u in us:
            md.append(f"Unknown: {u['question']}. How to obtain: {u['how_to_obtain']}.")
            md.append("")
    md.append("## 3. Unknowns and how to obtain them")
    if unknowns:
        md.append(table(["Area", "Question", "How to obtain"], [[AREA_TITLES[u["area"]], u["question"], u["how_to_obtain"]] for u in unknowns]))
    else:
        md.append("Every check produced evidence.")
    md.append("")
    md.append("## 4. Prioritized recommendations")
    md.append("Order: severity first, then the smallest effort first, so quick high value fixes come before long projects.")
    md.append("")
    md.append(table(["Priority", "Id", "Action", "Severity", "Effort", "Area", "Evidence"],
                    [[i, f"`{f['id']}`", f["recommendation"], f["severity"], f["effort"], AREA_TITLES[f["area"]], ", ".join(f"`{e}`" for e in f["evidence"])] for i, f in enumerate(ranked, 1)]))
    md.append("")
    md.append("## Appendix A: Evidence")
    md.append("Each block is the query that was run and the rows it returned at collection time. A block marked failed records the server's error so the missing permission can be granted and the check rerun.")
    md.append("")
    for area in AREAS:
        md.append(f"### {AREA_TITLES[area]}")
        for key, blk in ev.get(area, {}).items():
            md.append(f"#### `{area}.{key}`")
            if blk.get("sql"):
                md.append("```sql")
                md.append(blk["sql"])
                md.append("```")
            if blk.get("ok"):
                md.append(rows_table(blk.get("rows", [])))
            else:
                md.append(f"Failed: `{cell(blk.get('error', 'unknown error'), 300)}`")
            md.append("")
    return "\n".join(md) + "\n"


def platform_record(engine: str, ev: dict, host: str, port: int) -> dict:
    """Small structured summary for the inventory store."""
    v = (ev["inventory"].get("version", {}).get("rows") or [{}])[0]
    if engine == "postgres":
        version, flavour = v.get("server_version", "unknown"), "PostgreSQL"
        dbs = [{"name": d["datname"], "size_bytes": int(d.get("size_bytes") or 0)} for d in ev["inventory"].get("databases", {}).get("rows") or []]
    else:
        version = v.get("version", "unknown")
        flavour = "MariaDB" if "mariadb" in (str(version) + str(v.get("flavour", ""))).lower() else "MySQL"
        dbs = [{"name": d["db"], "size_bytes": int(d.get("size_bytes") or 0)} for d in ev["inventory"].get("databases", {}).get("rows") or []]
    return {"engine": engine, "flavour": flavour, "version": str(version), "host": host, "port": int(port), "databases": dbs}


def dump_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(jsonable(obj), fh, indent=2, ensure_ascii=False)
