import os
import sys

# Allow running directly as `python db/migrate.py`:
# when launched as a script, sys.path[0] is backend/db, which breaks the
# `from db.session import engine` import below. Add the backend root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import engine
from db.models import Base


def _text(sql: str):
    from sqlalchemy import text
    return text(sql)


def _column_max_length(table: str, column: str) -> int:
    """Return the current character_maximum_length of a column, or None."""
    q = (
        "SELECT character_maximum_length "
        "FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    )
    with engine.connect() as conn:
        return conn.execute(_text(q), {"t": table, "c": column}).scalar()


def _run_postgres_migrations() -> int:
    """Apply non-destructive ALTER TABLE changes to an existing PostgreSQL DB.

    SQLAlchemy create_all() only creates MISSING tables; it never alters
    existing ones, so schema fixes that must reach a pre-existing database
    have to be applied with explicit ALTER TABLE statements. This function
    is idempotent: each statement is skipped once the column is already at
    the target size.

    Fix added here (the failing insert was into document_analyses):
      - document_analyses.generated_at
        Old type: character varying(30)
        Failure:   value too long for type character varying(30)
        Cause:     a UTC ISO-8601 timestamp WITH microseconds is 32 chars
                   ("2026-08-19T05:28:14.915696+00:00") and did not fit the
                   VARCHAR(30) column when saving a document analysis.
        Fix:       widen the column to VARCHAR(40) to match the model.
    """
    if engine.dialect.name != "postgresql":
        return 0

    applied = 0

    # keep in sync with db/models.py DocumentAnalysis.generated_at
    if (_column_max_length("document_analyses", "generated_at") or 0) < 40:
        with engine.begin() as conn:
            conn.execute(
                _text(
                    "ALTER TABLE document_analyses "
                    "ALTER COLUMN generated_at TYPE VARCHAR(40)"
                )
            )
        applied += 1

    return applied


def create_tables_if_needed():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully.")
        migrated = _run_postgres_migrations()
        if migrated:
            print(f"PostgreSQL schema migrations applied ({migrated}).")
    except Exception as e:
        print("Error creating database:", e)
        raise


if __name__ == "__main__":
    create_tables_if_needed()
    print("Migration run complete.")
