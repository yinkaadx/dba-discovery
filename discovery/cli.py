"""Command line: run a discovery, re assess stored evidence, and maintain the inventory.

  python -m discovery run --engine postgres --dsn postgresql://user:pw@host:5432/db --name prod-pg-01 --environment production --owner "data platform"
  python -m discovery run --engine mysql --dsn mysql://user:pw@host:3306/db --name prod-mysql-01
  python -m discovery assess --run runs/prod-pg-01
  python -m discovery diff --a runs/prod-pg-01 --b runs/prod-pg-01-after
  python -m discovery inventory load --store inventory/inventory.sqlite --run runs/prod-pg-01
  python -m discovery inventory list --store inventory/inventory.sqlite
  python -m discovery inventory findings --store inventory/inventory.sqlite --severity High
  python -m discovery inventory status --store inventory/inventory.sqlite --run-name prod-pg-01 --code PG-SEC-001 --status done
  python -m discovery inventory export --store inventory/inventory.sqlite --out inventory/platforms.csv
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from urllib.parse import urlparse, unquote

from . import inventory as inv
from .report import dump_json, platform_record, render, jsonable
from .rules import assess


def _target(engine: str, dsn: str) -> tuple[str, int, str]:
    u = urlparse(dsn)
    host = u.hostname or "localhost"
    port = u.port or (5432 if engine == "postgres" else 3306)
    return host, port, unquote(u.username or "")


def _mysql_dsn(dsn: str) -> dict:
    u = urlparse(dsn)
    return {"host": u.hostname or "localhost", "port": u.port or 3306, "user": unquote(u.username or ""), "password": unquote(u.password or ""), "database": (u.path or "/").lstrip("/") or None}


def cmd_run(args) -> int:
    engine = args.engine
    host, port, user = _target(engine, args.dsn)
    run_name = args.name or f"{engine}-{host}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M')}"
    out_dir = os.path.join(args.out, run_name)
    os.makedirs(out_dir, exist_ok=True)
    collected_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if engine == "postgres":
        from .collectors_pg import collect
        ev = collect(args.dsn)
    else:
        from .collectors_mysql import collect
        ev = collect(_mysql_dsn(args.dsn))
    ev = jsonable(ev)
    ctx = assess(engine, ev)
    findings = [f.as_dict() for f in ctx.findings]
    unknowns = [u.as_dict() for u in ctx.unknowns]
    dump_json(os.path.join(out_dir, "evidence.json"), ev)
    dump_json(os.path.join(out_dir, "findings.json"), {"findings": findings, "unknowns": unknowns})
    run = {"run_name": run_name, "engine": engine, "collected_at": collected_at, "collector_user": user, "target": f"{host}:{port}",
           "environment": args.environment, "owner": args.owner, "platform": platform_record(engine, ev, host, port)}
    dump_json(os.path.join(out_dir, "run.json"), run)
    md = render(engine, f"{host}:{port}", run_name, collected_at, user, ev, findings, unknowns)
    with open(os.path.join(out_dir, "wiki.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    failed = sum(1 for a in ev.values() for b in a.values() if not b.get("ok"))
    total = sum(len(a) for a in ev.values())
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ("High", "Medium", "Low", "Info")}
    print(f"run {run_name}: {total - failed} of {total} evidence blocks collected, {len(findings)} findings (High {counts['High']}, Medium {counts['Medium']}, Low {counts['Low']}, Info {counts['Info']}), {len(unknowns)} unknowns")
    print(f"wrote {out_dir}/evidence.json, findings.json, run.json, wiki.md")
    return 0


def cmd_assess(args) -> int:
    with open(os.path.join(args.run, "run.json"), "r", encoding="utf-8") as fh:
        run = json.load(fh)
    with open(os.path.join(args.run, "evidence.json"), "r", encoding="utf-8") as fh:
        ev = json.load(fh)
    ctx = assess(run["engine"], ev)
    findings = [f.as_dict() for f in ctx.findings]
    unknowns = [u.as_dict() for u in ctx.unknowns]
    dump_json(os.path.join(args.run, "findings.json"), {"findings": findings, "unknowns": unknowns})
    md = render(run["engine"], run["target"], run["run_name"], run["collected_at"], run.get("collector_user", ""), ev, findings, unknowns)
    with open(os.path.join(args.run, "wiki.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"re assessed {run['run_name']}: {len(findings)} findings, {len(unknowns)} unknowns; wiki.md rewritten")
    return 0


def cmd_diff(args) -> int:
    """Compare two runs of the same platform: which findings are new, which were resolved, which remain."""
    def load(run_dir):
        with open(os.path.join(run_dir, "findings.json"), "r", encoding="utf-8") as fh:
            return {f["title"]: f for f in json.load(fh)["findings"]}
    a, b = load(args.a), load(args.b)
    resolved = sorted(set(a) - set(b))
    new = sorted(set(b) - set(a))
    remaining = sorted(set(a) & set(b))
    print(f"comparing {args.a} (before) with {args.b} (after)")
    print(f"resolved {len(resolved)}, new {len(new)}, remaining {len(remaining)}")
    for t in resolved:
        print(f"  resolved  {a[t]['id']:<12} {a[t]['severity']:<7} {t}")
    for t in new:
        print(f"  new       {b[t]['id']:<12} {b[t]['severity']:<7} {t}")
    for t in remaining:
        print(f"  remaining {b[t]['id']:<12} {b[t]['severity']:<7} {t}")
    return 0


def cmd_inventory(args) -> int:
    conn = inv.connect(args.store)
    if args.inv_cmd == "load":
        r = inv.load_run(conn, args.run)
        print(f"loaded {args.run}: platform {r['platform_id']}, run {r['run_id']}, {r['findings']} findings (High {r['High']}, Medium {r['Medium']}, Low {r['Low']}), {r['unknowns']} unknowns")
    elif args.inv_cmd == "list":
        print(inv.text_table(inv.platforms(conn), ["flavour", "version", "host", "port", "environment", "owner", "databases", "size_bytes", "latest_run", "open_high", "open_medium", "open_low", "open_unknowns"]))
    elif args.inv_cmd == "findings":
        print(inv.text_table(inv.open_findings(conn, args.severity), ["flavour", "host", "run_name", "code", "severity", "effort", "title", "status", "owner", "due"]))
    elif args.inv_cmd == "status":
        n = inv.set_status(conn, args.run_name, args.code, args.status, args.owner, args.due)
        print(f"updated {n} finding(s)")
    elif args.inv_cmd == "export":
        n = inv.export_csv(conn, args.out)
        print(f"exported {n} platform(s) to {args.out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="discovery", description="Read only database discovery for PostgreSQL and MySQL or MariaDB")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="collect evidence, assess, write the wiki page")
    r.add_argument("--engine", choices=["postgres", "mysql"], required=True)
    r.add_argument("--dsn", required=True, help="postgresql://user:pw@host:port/db or mysql://user:pw@host:port/db")
    r.add_argument("--name", help="run name; default engine-host-timestamp")
    r.add_argument("--out", default="runs")
    r.add_argument("--environment")
    r.add_argument("--owner")
    r.set_defaults(fn=cmd_run)
    a = sub.add_parser("assess", help="re run the rules over stored evidence and rewrite the wiki page")
    a.add_argument("--run", required=True)
    a.set_defaults(fn=cmd_assess)
    d = sub.add_parser("diff", help="compare two runs: resolved, new and remaining findings")
    d.add_argument("--a", required=True, help="earlier run directory")
    d.add_argument("--b", required=True, help="later run directory")
    d.set_defaults(fn=cmd_diff)
    i = sub.add_parser("inventory", help="maintain the platform inventory")
    store = argparse.ArgumentParser(add_help=False)
    store.add_argument("--store", default="inventory/inventory.sqlite", help="SQLite file; created with the schema on first use")
    isub = i.add_subparsers(dest="inv_cmd", required=True)
    il = isub.add_parser("load", parents=[store]); il.add_argument("--run", required=True)
    isub.add_parser("list", parents=[store])
    if_ = isub.add_parser("findings", parents=[store]); if_.add_argument("--severity", choices=["High", "Medium", "Low", "Info"])
    ist = isub.add_parser("status", parents=[store]); ist.add_argument("--run-name", required=True); ist.add_argument("--code", required=True)
    ist.add_argument("--status", required=True, choices=["open", "accepted", "in_progress", "done", "risk_accepted"]); ist.add_argument("--owner"); ist.add_argument("--due")
    ie = isub.add_parser("export", parents=[store]); ie.add_argument("--out", default="inventory/platforms.csv")
    i.set_defaults(fn=cmd_inventory)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
