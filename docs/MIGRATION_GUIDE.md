# Database Migration Guide

This platform uses **Alembic** for formal migrations and a **db_patch.sql** for interim schema changes across all tenant schemas.

## Architecture

| Component        | Location                          | Role                                       |
| ---------------- | --------------------------------- | ------------------------------------------ |
| Alembic config   | `backend/alembic.ini`             | Alembic settings, file naming template     |
| Env config       | `backend/migrations/env.py`       | Multi-tenant schema wiring                 |
| Version files    | `backend/migrations/versions/`    | Formal migration chain                     |
| DB patch         | `backend/migrations/db_patch.sql` | Idempotent interim DDL + version stamp     |
| Migration script | `scripts/migration.sh`            | Orchestrates everything across all tenants |

## Key Concepts

- **Schema-per-tenant**: Each org has its own Postgres schema. Migrations run once per schema.
- **DB patch**: Used for minor interim changes between formal migrations. Always idempotent (`IF NOT EXISTS`, `IF EXISTS`).
- **Version stamp**: The patch always stamps `alembic_version` to the latest migration revision as a safety net.

## Running Migrations

```bash
# All schemas (auto-discovered)
./scripts/migration.sh

# Specific schemas
./scripts/migration.sh schema1 schema2
```

The script runs in order:

1. `alembic upgrade head` per schema
2. Checkpointer migrations per schema
3. `db_patch.sql` once (patch loops all schemas internally)

## Day-to-Day Workflows

### Minor change (new column, default change, index, etc.)

1. Update your SQLAlchemy model
2. Add idempotent DDL to `backend/migrations/db_patch.sql` between the START/END markers:
   ```sql
   ALTER TABLE IF EXISTS my_table
       ADD COLUMN IF NOT EXISTS new_col JSONB;
   ```
3. Backfill the same DDL into the **current latest migration file's** `upgrade()` so the migration chain stays self-contained for new tenants
4. Version stamp in the patch stays unchanged (it already points to the latest migration)
5. Deploy and run `./scripts/migration.sh`

### Major change (new tables, foreign keys, data migrations)

1. Update your SQLAlchemy models (for both the new feature and any pending patch changes)
2. Generate a new migration:
   ```bash
   cd backend
   alembic revision --autogenerate -m "short_description"
   ```
   Autogenerate will only pick up the new feature DDL — patch changes are already in the DB and backfilled into the previous migration, so they produce no diff. This is expected.
3. Clear the patch DDL section in `db_patch.sql` (keep the boilerplate loop and exception handling)
4. Update the version stamp in `db_patch.sql` to the new migration's revision ID
5. Deploy and run `./scripts/migration.sh`

### Provisioning a new tenant

No special steps. `./scripts/migration.sh new_schema` runs the full migration chain + patch. `env.py` auto-creates the schema if it doesn't exist.

## When to Create a Migration vs. Use the Patch

| Use patch (+ backfill)  | Create new migration                     |
| ----------------------- | ---------------------------------------- |
| `ADD/DROP COLUMN`       | New tables or foreign keys               |
| Default value changes   | Data migrations (`UPDATE` existing rows) |
| Adding/removing indexes | Constraint changes (NOT NULL, UNIQUE)    |
|                         | Renaming columns or tables               |
|                         | Any DDL that's hard to make idempotent   |

**Rule of thumb**: If you can write it with `IF NOT EXISTS` / `IF EXISTS` guards, it can go in the patch. Otherwise, create a migration.

## Rules

1. **Patch DDL must be idempotent.** It may run multiple times across deploys.
2. **Always backfill patch DDL into the current latest migration.** This keeps the migration chain self-contained — a new tenant running the full chain must get every change without depending on the patch.
3. **Version stamp = latest migration revision.** Update it only when creating a new migration.
4. **Test on a clean schema.** After creating a new migration, verify by running the full chain against an empty schema to confirm new tenant provisioning works.
5. **Don't create migrations for trivial changes.** Use the patch + backfill workflow to avoid accumulating many small version files.
