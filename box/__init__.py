"""BOX (Blue Ox) type-curve build — batch jobs over the oilgas warehouse.

Plan of record: docs/box_type_curves_plan.md. Each step ships as a module here
plus a thin CLI in scripts/box_*.py. Read-only steps use the ETL session pooler
(etl.db.get_connection) inside a READ ONLY transaction; nothing in this package
writes to the warehouse without an explicit go-apply.
"""
