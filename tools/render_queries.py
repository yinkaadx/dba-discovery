"""Generate the manual query catalogue in the skill references from the collector source, so the two never drift.

  python tools/render_queries.py
"""
from __future__ import annotations

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AREA_VARS = {"i": "inventory", "a": "architecture", "h": "ha_dr", "cm": "change_management", "s": "security", "ac": "access", "b": "backup", "c": "cost", "m": "monitoring", "o": "operations"}


def extract(path: str):
    """Return [(area, key, kind, sql_or_names)] in source order by walking assignments in collect()."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = []
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "collect"][0]
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in AREA_VARS and isinstance(t.slice, ast.Constant)):
            continue
        area, key = AREA_VARS[t.value.id], t.slice.value
        v = node.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "q" and len(v.args) >= 2 and isinstance(v.args[1], ast.Constant):
            out.append((area, key, "sql", v.args[1].value))
        elif isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ("settings", "variables"):
            names = [e.value for e in v.args[1].elts]
            out.append((area, key, v.func.id, names))
        elif isinstance(v, ast.Name):  # temporary variable filled by a q() call with fallbacks
            first = [n for n in ast.walk(fn) if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == v.id
                     and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == "q" and isinstance(n.value.args[1], ast.Constant)]
            out.append((area, key, "fallback", first[0].value.args[1].value if first else ""))
        elif isinstance(v, ast.Subscript) and isinstance(v.value, ast.Name) and v.value.id in AREA_VARS and isinstance(v.slice, ast.Constant):
            out.append((area, key, "alias", f"{AREA_VARS[v.value.id]}.{v.slice.value}"))
        elif isinstance(v, ast.Dict):
            out.append((area, key, "note", ""))
    return out


def render(path: str, engine: str) -> str:
    items = extract(path)
    lines = []
    for area, key, kind, val in items:
        lines.append(f"### `{area}.{key}`")
        if kind == "sql":
            lines.append("```sql")
            lines.append(val.strip())
            lines.append("```")
        elif kind == "settings":
            lines.append("```sql")
            lines.append("SELECT name, setting, unit, source FROM pg_settings WHERE name IN (" + ", ".join(f"'{n}'" for n in val) + ") ORDER BY name;")
            lines.append("```")
        elif kind == "variables":
            lines.append("```sql")
            lines.append("SHOW GLOBAL VARIABLES WHERE Variable_name IN (" + ", ".join(f"'{n}'" for n in val) + ");")
            lines.append("```")
        elif kind == "alias":
            lines.append(f"Same rows as `{val}` (the collector reuses that result).")
        elif kind == "fallback":
            lines.append("First attempt (the collector falls back to the alternatives named above the catalogue when this fails):")
            lines.append("```sql")
            lines.append(val.strip())
            lines.append("```")
        elif kind == "note":
            lines.append("Not a query: a reminder that this evidence comes from people and tooling outside the server.")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    pg = render(os.path.join(ROOT, "discovery", "collectors_pg.py"), "postgres")
    my = render(os.path.join(ROOT, "discovery", "collectors_mysql.py"), "mysql")
    for name, body in (("postgres-access.md", pg), ("mysql-access.md", my)):
        p = os.path.join(ROOT, "skills", "dba-discovery", "reference", name)
        text = open(p, encoding="utf-8").read()
        start, end = "<!-- queries:start -->", "<!-- queries:end -->"
        head, rest = text.split(start)
        _, tail = rest.split(end)
        open(p, "w", encoding="utf-8").write(head + start + "\n" + body + end + tail)
        print("updated", p)
