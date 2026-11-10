"""Behaviour check of sql/72 + sql/16 + sql/23 on a THROWAWAY Postgres/PostGIS (never Supabase).

    docker run --rm -d --name tagrule-sqlcheck -p 55432:5432 -e POSTGRES_PASSWORD=check postgis/postgis:16-3.4
    python -m scripts.tag_rule_sqlcheck "host=localhost port=55432 user=postgres password=check dbname=postgres"
    docker stop tagrule-sqlcheck

Builds stub curated.wells / crosswalk / overrides / producing_reference, applies the three files verbatim and asserts:
switch OFF = vendor tags (+ the override); switch ON = a matching rule row applies (source rule_step1) while a stale
TVD, a changed planned flag, a human call and a well without a row keep their non-rule tags; sql/23 flips a depth
outlier with the switch OFF but never a human call, and flips nothing with the switch ON; REFRESH CONCURRENTLY works.
Refuses any DSN that does not name localhost.
"""

import sys
from pathlib import Path

import psycopg


def main(dsn: str) -> int:
    if "localhost" not in dsn and "127.0.0.1" not in dsn:
        raise SystemExit("throwaway local databases only")
    c = psycopg.connect(dsn, autocommit=True)
    x = c.execute
    x = c.execute
    x("DROP SCHEMA IF EXISTS curated, ref, meta, extensions CASCADE")
    x("CREATE EXTENSION IF NOT EXISTS postgis; CREATE SCHEMA curated; CREATE SCHEMA ref; CREATE SCHEMA meta; CREATE SCHEMA extensions;")
    x("""CREATE TABLE curated.wells (api10 text, formation varchar(64), env_interval text, subbasin text, env_basin text,
         tvd_ft int, directional_survey_is_planned boolean)""")
    x("CREATE TABLE ref.formation_crosswalk (basin text, source text, raw_value text, canonical_code text, notes text)")
    x("CREATE TABLE ref.formation_tag_overrides (api10 text PRIMARY KEY, corrected_code text NOT NULL, was text, note text)")
    x("""INSERT INTO ref.formation_crosswalk VALUES ('delaware','novi','THIRD BONE SPRING LIME','BS3_C',''),
         ('delaware','enverus','2ND BONE SPRING SAND','BS2_S','')""")
    for a,t,p in [("A",8010,False),("B",8010,False),("C",8010,False),("D",8010,False),("P",8010,True)]:
        x("INSERT INTO curated.wells VALUES (%s,'THIRD BONE SPRING LIME','2ND BONE SPRING SAND','Delaware Basin',NULL,%s,%s)",(a,t,p))
    x("INSERT INTO ref.formation_tag_overrides VALUES ('C','WCA_1','BS3_C','test')")
    sql = lambda n: (Path(__file__).resolve().parent.parent / "sql" / n).read_text(encoding="utf-8")
    x(sql("72_formation_tag_rule.sql")); x(sql("72_formation_tag_rule.sql"))
    x(sql("16_formation_blueox.sql"))
    def row(a, tvd, planned=False):
        x("""INSERT INTO curated.formation_tag_rule (api10,basin,applied,applied_code,applied_step,vendor_code,step1_queue,step2_queue,
             step3_queue,novi_raw,env_raw,tvd_ft,planned,in_box_extents,run_id) VALUES (%s,'delaware',TRUE,'BS2_S',1,'BS3_C',FALSE,FALSE,
             FALSE,'THIRD BONE SPRING LIME','2ND BONE SPRING SAND',%s,%s,TRUE,1)""",(a,tvd,planned))
    row("A",8010); row("B",8100); row("C",8010); row("P",8010,False)
    def tags():
        x("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox")
        return {a: (t, s) for a, t, s in x("SELECT api10, formation_blueox, formation_blueox_source FROM curated.formation_blueox").fetchall()}
    off = tags()
    assert off == {"A": ("BS3_C", "novi"), "B": ("BS3_C", "novi"), "C": ("WCA_1", "ratified_override"), "D": ("BS3_C", "novi"), "P": ("BS3_C", "novi")}, off
    x("UPDATE ref.formation_tag_switch SET use_rule = TRUE")
    on = tags()
    assert on == {**off, "A": ("BS2_S", "rule_step1")}, on
    x("UPDATE ref.formation_tag_switch SET use_rule = FALSE")
    x("CREATE TABLE curated.producing_reference (api10 text, basin text, code text, tvd int, survey_planned boolean, geom geometry(Point,4326))")
    pts = [(f"s{i}","BS2_S",8001+i,0.001*i) for i in range(6)] + [(f"c{i}","BS3_C",9001+i,0.001*i) for i in range(4)] + [("E","BS2_S",9010,0.0005),("F","BS2_S",9011,0.0006)]
    for a,code,tvd,dx in pts:
        x("INSERT INTO curated.producing_reference VALUES (%s,'delaware',%s,%s,FALSE,ST_SetSRID(ST_MakePoint(-103.5+%s,31.5),4326))",(a,code,tvd,dx))
    x("INSERT INTO ref.formation_tag_overrides VALUES ('F','BS2_S','BS2_S','test human call')")
    x(sql("23_formation_blueox_tvd.sql"))
    flips = x("SELECT api10, corrected_code FROM curated.formation_blueox_tvd WHERE corrected ORDER BY 1").fetchall()
    assert flips == [("E", "BS3_C")], flips  # F, the human call, is never flipped
    x("UPDATE ref.formation_tag_switch SET use_rule = TRUE")
    x("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox_tvd")
    assert x("SELECT count(*) FROM curated.formation_blueox_tvd WHERE corrected").fetchone()[0] == 0
    print("sql/72 + sql/16 + sql/23 behaviour: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
