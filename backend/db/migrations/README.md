Alembic migration files.

Baseline revision:
- `versions/20260217_0001_initial.py`

Use:
- `alembic -c backend/db/alembic.ini upgrade head`

Runtime table auto-create is controlled by `AUTO_CREATE_TABLES` and should be disabled in production.
