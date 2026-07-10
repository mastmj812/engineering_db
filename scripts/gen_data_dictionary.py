"""Generate docs/DATA_DICTIONARY.md from the live warehouse catalog.

The dictionary is INTROSPECTED, not hand-written: relation and column
descriptions come from Postgres COMMENTs (sql/31_comments.sql), the
matview list and refresh cadence come from etl.db, and lineage comes
from pg_depend/pg_rewrite. Re-run after any schema change; the doc can
only rot if sql/31 rots.

Usage (repo root, venv):
    python -m scripts.gen_data_dictionary            # writes docs/DATA_DICTIONARY.md
    python -m scripts.gen_data_dictionary --json PATH  # also dump the raw model as JSON
    python -m scripts.gen_data_dictionary --html PATH  # also emit the shareable HTML page
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from etl.db import _CURATED_MATVIEWS, _GATED_REFRESH, get_connection

DOCS = Path(__file__).resolve().parent.parent / "docs"

# Schemas documented, in reading order (raw -> curated -> ops).
SCHEMAS = (
    "raw_novi",
    "raw_enverus",
    "raw_intel",
    "raw_novi_intel",
    "ref",
    "curated",
    "meta",
)

_KIND = {"r": "table", "v": "view", "m": "materialized view"}

# Rebuilt (DROP + CREATE) by the quarterly Novi Intelligence reload chain,
# not the nightly refresh. Keep in sync with the reload runbook.
_QUARTERLY = {
    "curated.intel_formation_blueox",
    "curated.reconciled_inventory",
    "curated.net_new_pdp",
    "curated.intel_arps",
    "curated.intel_forecast",
}

# Primary downstream consumers, maintained by hand (small on purpose).
_CONSUMERS = {
    "curated.wells_enriched": "anduin sync, erebor, narvi, ad-hoc analysis",
    "curated.production_normalized": "anduin type-curve fitting",
    "curated.production_forecast": "anduin (Novi ML forecast overlay)",
    "curated.type_curve_cohorts": "legacy delaware_basin_eval",
    "curated.intel_locations": "erebor Highgrade/facets/export",
    "curated.reconciled_inventory": "narvi remaining inventory, erebor recon status",
    "curated.erebor_locations": "erebor tiles/selection, land team direct GIS",
}


def _cadence(rel: str, kind: str) -> str:
    """Human cadence string for a relation, derived from etl.db where possible."""
    schema = rel.split(".")[0]
    if schema in ("raw_novi", "raw_enverus"):
        return "nightly (scripts.run_daily raw load)"
    if schema == "raw_intel":
        return "quarterly (scripts.load_intel_sf, Novi Snowflake share)"
    if schema == "raw_novi_intel":
        return "static (frozen overlay geometries from the 3Q25 file drop; share has no geometry)"
    if schema == "meta":
        return "continuous (ETL bookkeeping)"
    if schema == "ref":
        return "static reference"
    if rel in _CURATED_MATVIEWS:
        pos = _CURATED_MATVIEWS.index(rel) + 1
        gated = " — refresh gated on source change" if rel in _GATED_REFRESH else ""
        note = (
            " (also DROP+recreated by the quarterly intel reload)"
            if rel in ("curated.intel_locations", "curated.erebor_locations")
            else ""
        )
        return f"nightly (etl.refresh, {pos}/{len(_CURATED_MATVIEWS)}){gated}{note}"
    if rel in _QUARTERLY:
        return "quarterly (Novi intel reload chain)"
    if kind == "view":
        return "n/a (plain view, always current)"
    return "on demand"


def introspect() -> dict[str, Any]:
    conn = get_connection()
    model: dict[str, Any] = {"generated": date.today().isoformat(), "schemas": {}}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT n.nspname, c.relname, c.relkind, d.description,
                       c.reltuples::bigint
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_description d
                       ON d.objoid = c.oid AND d.objsubid = 0
                WHERE n.nspname = ANY(%s) AND c.relkind IN ('r','v','m')
                ORDER BY n.nspname, c.relname
                """,
                (list(SCHEMAS),),
            )
            for schema, rel, kind, desc, rows in cur.fetchall():
                model["schemas"].setdefault(schema, {})[rel] = {
                    "kind": _KIND[kind],
                    "comment": desc,
                    "rows_est": max(rows, 0),
                    "columns": [],
                    "reads_from": [],
                }

            cur.execute(
                """
                SELECT n.nspname, c.relname, a.attname,
                       format_type(a.atttypid, a.atttypmod), d.description
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid AND c.relkind IN ('r','v','m')
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_description d
                       ON d.objoid = c.oid AND d.objsubid = a.attnum
                WHERE n.nspname = ANY(%s)
                  AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY n.nspname, c.relname, a.attnum
                """,
                (list(SCHEMAS),),
            )
            for schema, rel, col, typ, desc in cur.fetchall():
                model["schemas"][schema][rel]["columns"].append(
                    {"name": col, "type": typ, "comment": desc}
                )

            # View/matview lineage via rewrite rules: relation -> relations it reads.
            cur.execute(
                """
                SELECT DISTINCT dn.nspname || '.' || dc.relname AS dependent,
                       sn.nspname || '.' || sc.relname AS source
                FROM pg_rewrite rw
                JOIN pg_class dc ON dc.oid = rw.ev_class
                JOIN pg_namespace dn ON dn.oid = dc.relnamespace
                JOIN pg_depend dep ON dep.objid = rw.oid
                     AND dep.refclassid = 'pg_class'::regclass
                JOIN pg_class sc ON sc.oid = dep.refobjid
                     AND sc.relkind IN ('r','v','m')
                JOIN pg_namespace sn ON sn.oid = sc.relnamespace
                WHERE dn.nspname = ANY(%s)
                  AND dc.oid <> sc.oid
                ORDER BY 1, 2
                """,
                (list(SCHEMAS),),
            )
            for dependent, source in cur.fetchall():
                schema, rel = dependent.split(".", 1)
                entry = model["schemas"].get(schema, {}).get(rel)
                if entry is not None:
                    entry["reads_from"].append(source)
    finally:
        conn.close()
    return model


def render(model: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# oilgas data dictionary")
    out.append("")
    out.append(
        f"*Generated {model['generated']} by `scripts/gen_data_dictionary.py` "
        "from the live catalog — do not hand-edit. Descriptions are Postgres "
        "COMMENTs (`sql/31_comments.sql`); re-run this script after schema "
        "changes.*"
    )
    out.append("")
    out.append("## Data flow")
    out.append("")
    out.append(
        "**Novi Insights (nightly) + Enverus (nightly) + Novi Intelligence "
        "(quarterly Snowflake share) -> raw schemas -> `curated` matviews -> "
        "apps (anduin / erebor / narvi) and direct read-only users.** "
        "Nightly: `scripts.run_daily` loads raw then refreshes the curated "
        "matviews in dependency order. Quarterly: the intel reload chain "
        "rebuilds the intel-derived matviews "
        "(`load_intel_sf` -> `apply_intel_formation_blueox` -> "
        "`apply_reconciled_inventory` -> `apply_erebor_locations`). "
        "The `narvi` schema is app-owned and not documented here."
    )
    out.append("")
    out.append("## Conventions that affect interpretation")
    out.append("")
    for conv in (
        "`api10` is the universal well key; Novi <-> Enverus join is "
        "`LEFT(api14, 10) = api10`.",
        "Formation grouping always uses `formation_blueox`, never raw "
        "free-text `formation`.",
        "Rates for fitting/aggregation are calendar-day (`rate_calday_*`); "
        "`rate_prodday_*` is a per-well diagnostic.",
        "Novi NPV/IRR columns are a vendor screen, not authoritative "
        "economics; economics happens downstream of exports.",
        "SPE percentiles: P10 = HIGH case, P90 = LOW case.",
    ):
        out.append(f"- {conv}")
    out.append("")

    for schema in SCHEMAS:
        rels = model["schemas"].get(schema, {})
        if not rels:
            continue
        out.append(f"## Schema `{schema}`")
        out.append("")
        for rel, info in rels.items():
            full = f"{schema}.{rel}"
            out.append(f"### `{full}` ({info['kind']})")
            out.append("")
            if info["comment"]:
                out.append(info["comment"])
                out.append("")
            meta = [f"~{info['rows_est']:,} rows", _cadence(full, info["kind"])]
            if info["reads_from"]:
                meta.append("reads: " + ", ".join(f"`{s}`" for s in info["reads_from"]))
            if full in _CONSUMERS:
                meta.append("consumers: " + _CONSUMERS[full])
            out.append(" | ".join(meta))
            out.append("")
            out.append("| column | type | description |")
            out.append("|---|---|---|")
            for c in info["columns"]:
                desc = (c["comment"] or "").replace("|", "\\|")
                out.append(f"| `{c['name']}` | {c['type']} | {desc} |")
            out.append("")
    return "\n".join(out) + "\n"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_HTML_HEAD = """<title>oilgas data dictionary</title>
<style>
:root{
  --paper:#FBFAF7; --ink:#232820; --muted:#6C7267; --rule:#E7E4DB;
  --accent:#14685A; --accent-soft:#E3EEEA;
  --amber:#8A6A1B; --amber-soft:#F3ECD9; --slate:#55606B; --slate-soft:#E6E9EC;
  --mono:"Cascadia Code",ui-monospace,Consolas,monospace;
}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto}}
body{background:var(--paper);color:var(--ink);margin:0;
  font:15px/1.55 "Segoe UI",system-ui,sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover,a:focus-visible{text-decoration:underline}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{display:grid;grid-template-columns:264px minmax(0,1fr);gap:0;min-height:100vh}
nav{border-right:1px solid var(--rule);padding:20px 0 40px;
  position:sticky;top:0;height:100vh;overflow-y:auto;background:#F6F4EE}
nav h2{font-size:11px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);margin:18px 20px 4px;font-weight:600}
nav a{display:flex;align-items:center;gap:8px;padding:3px 20px;color:var(--ink);
  font-size:13.5px;border-left:2px solid transparent}
nav a:hover{background:var(--accent-soft);text-decoration:none}
nav .dot{width:7px;height:7px;border-radius:50%;flex:none}
.dot.m{background:var(--accent)} .dot.v{background:var(--amber)} .dot.r{background:var(--slate)}
main{padding:28px 40px 80px;max-width:1020px}
header.page h1{font-size:26px;font-weight:650;letter-spacing:-.01em;margin:0 0 6px;
  text-wrap:balance}
header.page p{color:var(--muted);max-width:68ch;margin:.3em 0}
.conv{border:1px solid var(--rule);background:#F6F4EE;padding:12px 18px;margin:18px 0 8px}
.conv ul{margin:.3em 0;padding-left:1.2em}
.conv li{margin:.15em 0}
.search{position:sticky;top:0;background:var(--paper);padding:14px 0 10px;z-index:5;
  border-bottom:1px solid var(--rule);margin-bottom:8px}
.search input{width:100%;box-sizing:border-box;font:inherit;padding:9px 14px;
  border:1.5px solid var(--rule);border-radius:4px;background:#fff;color:var(--ink)}
.search input:focus{outline:none;border-color:var(--accent)}
.search .hint{font-size:12.5px;color:var(--muted);margin-top:5px}
h2.schema{font-size:12px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin:38px 0 6px;
  border-bottom:1px solid var(--rule);padding-bottom:5px}
section.rel{margin:0 0 26px;border:1px solid var(--rule);background:#fff}
section.rel > .hd{padding:13px 18px 11px;border-bottom:1px solid var(--rule)}
.hd h3{margin:0;font-size:16.5px;font-weight:650;font-family:var(--mono)}
.chip{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.05em;
  text-transform:uppercase;padding:1px 8px;border-radius:9px;vertical-align:2px;margin-left:8px}
.chip.m{background:var(--accent-soft);color:var(--accent)}
.chip.v{background:var(--amber-soft);color:var(--amber)}
.chip.r{background:var(--slate-soft);color:var(--slate)}
.hd .desc{margin:7px 0 0;max-width:78ch}
.hd .meta{margin:8px 0 0;font-size:12.5px;color:var(--muted)}
.hd .meta b{color:var(--ink);font-weight:600}
.hd .meta .n{font-family:var(--mono);font-variant-numeric:tabular-nums}
.cols{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);
  text-align:left;font-weight:600;padding:8px 18px 6px;border-bottom:1px solid var(--rule)}
td{padding:5px 18px;border-bottom:1px solid #F1EFE8;vertical-align:top}
tr:last-child td{border-bottom:none}
td.c,td.t{font-family:var(--mono);font-size:12.5px;white-space:nowrap}
td.t{color:var(--muted)}
td.d{max-width:60ch}
.hidden{display:none}
mark{background:#F2E9C8;color:inherit;padding:0 1px}
.count{font-size:12.5px;color:var(--muted)}
</style>"""


def render_html(model: dict[str, Any]) -> str:
    nav: list[str] = []
    body: list[str] = []
    for schema in SCHEMAS:
        rels = model["schemas"].get(schema, {})
        if not rels:
            continue
        nav.append(f"<h2>{schema}</h2>")
        body.append(f'<h2 class="schema" data-schema="{schema}">{schema}</h2>')
        for rel, info in rels.items():
            full = f"{schema}.{rel}"
            kind_cls = {"table": "r", "view": "v", "materialized view": "m"}[info["kind"]]
            anchor = full.replace(".", "-")
            nav.append(
                f'<a href="#{anchor}"><span class="dot {kind_cls}"></span>{_esc(rel)}</a>'
            )
            meta = [
                f'<span class="n">~{info["rows_est"]:,}</span> rows',
                _esc(_cadence(full, info["kind"])),
            ]
            if info["reads_from"]:
                links = ", ".join(
                    f'<a href="#{s.replace(".", "-")}">{_esc(s)}</a>'
                    for s in info["reads_from"]
                )
                meta.append(f"<b>reads:</b> {links}")
            if full in _CONSUMERS:
                meta.append(f"<b>consumers:</b> {_esc(_CONSUMERS[full])}")
            rows = "".join(
                f'<tr><td class="c">{_esc(c["name"])}</td>'
                f'<td class="t">{_esc(c["type"])}</td>'
                f'<td class="d">{_esc(c["comment"] or "")}</td></tr>'
                for c in info["columns"]
            )
            body.append(
                f'<section class="rel" id="{anchor}" data-name="{_esc(full)}">'
                f'<div class="hd"><h3>{_esc(full)}'
                f'<span class="chip {kind_cls}">{_esc(info["kind"])}</span></h3>'
                + (f'<p class="desc">{_esc(info["comment"])}</p>' if info["comment"] else "")
                + f'<p class="meta">{" &middot; ".join(meta)}</p></div>'
                f'<div class="cols"><table><thead><tr><th>column</th><th>type</th>'
                f"<th>description</th></tr></thead><tbody>{rows}</tbody></table>"
                f"</div></section>"
            )

    conventions = "".join(
        f"<li>{c}</li>"
        for c in (
            "<b>api10</b> is the universal well key; Novi&harr;Enverus join is "
            "LEFT(api14,&nbsp;10) = api10.",
            "Formation grouping always uses <b>formation_blueox</b>, never the "
            "raw free-text formation.",
            "Rates for aggregation are <b>calendar-day</b>; producing-day rates "
            "are per-well diagnostics.",
            "Novi NPV/IRR columns are a vendor screen, <b>not authoritative "
            "economics</b>.",
            "SPE percentiles: <b>P10 = HIGH</b> case, P90 = LOW case.",
        )
    )
    n_rel = sum(len(r) for r in model["schemas"].values())
    n_col = sum(
        len(i["columns"]) for r in model["schemas"].values() for i in r.values()
    )
    return f"""{_HTML_HEAD}
<div class="wrap">
<nav aria-label="Relations">{"".join(nav)}</nav>
<main>
<header class="page">
<h1>oilgas data dictionary</h1>
<p>Blue Ox Permian data warehouse (Supabase Postgres + PostGIS). Data flow:
<b>Novi Insights (nightly) + Enverus (nightly) + Novi Intelligence (quarterly
Snowflake share) &rarr; raw schemas &rarr; curated matviews &rarr; apps and
read-only users.</b></p>
<p>Generated {model["generated"]} from the live catalog &middot; {n_rel}
relations &middot; {n_col:,} columns. Descriptions live in the database as
column comments &mdash; the same text appears in DBeaver, pgAdmin, QGIS, and
Supabase Studio.</p>
<div class="conv"><b>Read this first — conventions that change interpretation</b>
<ul>{conventions}</ul></div>
</header>
<div class="search"><input id="q" type="search"
  placeholder="Filter: relation, column, or description text&hellip;"
  aria-label="Filter relations and columns">
<div class="hint" id="hint">{n_rel} relations shown</div></div>
{"".join(body)}
</main>
</div>
<script>
const q = document.getElementById('q'), hint = document.getElementById('hint');
const sections = [...document.querySelectorAll('section.rel')].map(s => ({{
  el: s, name: s.dataset.name.toLowerCase(),
  text: s.textContent.toLowerCase(),
  nav: document.querySelector(`nav a[href="#${{s.id}}"]`),
}}));
const headers = [...document.querySelectorAll('h2.schema')];
const navHs = [...document.querySelectorAll('nav h2')];
q.addEventListener('input', () => {{
  const t = q.value.trim().toLowerCase();
  let shown = 0;
  for (const s of sections) {{
    const hit = !t || s.name.includes(t) || s.text.includes(t);
    s.el.classList.toggle('hidden', !hit);
    s.nav.classList.toggle('hidden', !hit);
    if (hit) shown++;
  }}
  for (const h of headers) {{
    const schema = h.dataset.schema;
    const any = sections.some(s => !s.el.classList.contains('hidden')
      && s.name.startsWith(schema + '.'));
    h.classList.toggle('hidden', !any);
  }}
  for (const h of navHs) {{
    const any = sections.some(s => !s.nav.classList.contains('hidden')
      && s.name.startsWith(h.textContent + '.'));
    h.classList.toggle('hidden', !any);
  }}
  hint.textContent = shown + ' relation' + (shown === 1 ? '' : 's') + ' shown';
}});
</script>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=None,
                        help="also dump the raw model as JSON to this path")
    parser.add_argument("--html", type=Path, default=None,
                        help="also emit the shareable HTML page to this path")
    args = parser.parse_args()

    model = introspect()
    md = render(model)
    target = DOCS / "DATA_DICTIONARY.md"
    target.write_text(md, encoding="utf-8")
    n_rel = sum(len(r) for r in model["schemas"].values())
    n_col = sum(
        len(i["columns"]) for r in model["schemas"].values() for i in r.values()
    )
    print(f"wrote {target}: {n_rel} relations, {n_col} columns")
    if args.json:
        args.json.write_text(json.dumps(model, indent=1), encoding="utf-8")
        print(f"wrote {args.json}")
    if args.html:
        args.html.write_text(render_html(model), encoding="utf-8")
        print(f"wrote {args.html}")


if __name__ == "__main__":
    main()
