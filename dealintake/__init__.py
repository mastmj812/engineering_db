"""deal-intake v2 runner — deterministic signals for the deal-intake skill.

The skill (.claude/skills/deal-intake/SKILL.md) is the operator playbook;
this package computes what the playbook says to compute, reproducibly per
config_version. Hard rules inherited from the workspace:

* Warehouse access is READ-ONLY (etl.db.get_connection, SELECT only).
* No economics. EUR is the raw 50-yr technical integral.
* Di is always reported nominal (/yr) AND 1-yr effective side by side.
* formation_blueox is the only bench key; api10 is the well key.
* Nothing here auto-drops a well or auto-decides a geological call: every
  signal is a flag or a recommendation for the reviewer.
"""
