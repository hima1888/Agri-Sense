"""Schema-level guarantees, verified against the migrated Postgres database."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import head_revision
from tests.conftest import migration_config

REQUIRED_TABLES = {
    "users", "farms", "farm_zones", "soil_profiles", "soil_measurements", "crops", "crop_cycles",
    "plants", "sensors", "sensor_readings", "weather_data", "irrigation_events",
    "fertilizer_applications", "pesticide_applications", "plant_detections", "disease_detections",
    "ai_predictions", "ai_recommendations", "alerts", "reports", "federated_learning_runs",
    "federated_clients", "model_versions", "audit_logs",
}  # fmt: skip
SUPPORTING_TABLES = {"devices", "federated_client_updates"}


def public_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names(schema="public")) - {"alembic_version"}


def test_all_required_tables_exist(engine: Engine) -> None:
    assert public_tables(engine) == REQUIRED_TABLES | SUPPORTING_TABLES


def test_database_is_at_head_revision(engine: Engine) -> None:
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head_revision()


def test_models_and_migrations_have_not_drifted(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], f"Models differ from migrations; generate a new revision: {diff}"


def test_row_level_security_enabled_on_every_table(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity "
                "AND c.relname <> 'alembic_version'"
            )
        ).scalars()
        assert list(rows) == []


def test_every_foreign_key_is_indexed(engine: Engine) -> None:
    """Unindexed FKs make joins and ON DELETE CASCADE scans slow."""
    query = text(
        """
        SELECT con.conrelid::regclass::text AS tbl, con.conname
        FROM pg_constraint con
        WHERE con.contype = 'f'
          AND con.connamespace = 'public'::regnamespace
          AND NOT EXISTS (
            SELECT 1 FROM pg_index i
            WHERE i.indrelid = con.conrelid
              AND (i.indkey::int2[])[0:cardinality(con.conkey) - 1] = con.conkey
          )
        """
    )
    with engine.connect() as conn:
        assert conn.execute(query).all() == []


def test_primary_keys_use_identity_or_uuid(engine: Engine) -> None:
    insp = inspect(engine)
    for table in public_tables(engine):
        pk_cols = insp.get_pk_constraint(table)["constrained_columns"]
        assert pk_cols == ["id"], table
        col = next(c for c in insp.get_columns(table) if c["name"] == "id")
        type_name = str(col["type"]).upper()
        assert type_name in {"BIGINT", "UUID"}, (table, type_name)
        if type_name == "BIGINT":
            assert col.get("identity") is not None, f"{table}.id should be an identity column"


def test_timestamps_are_timezone_aware(engine: Engine) -> None:
    insp = inspect(engine)
    for table in public_tables(engine):
        for col in insp.get_columns(table):
            if "TIMESTAMP" in str(col["type"]).upper():
                assert getattr(col["type"], "timezone", False), f"{table}.{col['name']} must be timestamptz"


def test_downgrade_and_upgrade_round_trip(engine: Engine) -> None:
    cfg = migration_config()
    command.downgrade(cfg, "base")
    try:
        assert public_tables(engine) == set()
        with engine.connect() as conn:
            fn = conn.execute(text("SELECT to_regproc('public.set_updated_at')")).scalar()
            assert fn is None
    finally:
        command.upgrade(cfg, "head")
    assert public_tables(engine) == REQUIRED_TABLES | SUPPORTING_TABLES
