import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.models import Base


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Explicitly select psycopg 3, including for an existing postgresql:// URL.
database_url = make_url(os.environ["DATABASE_URL"]).set(
    drivername="postgresql+psycopg"
)
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    hide_parameters=True,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create missing tables and keep them accessible only to the backend."""
    with engine.begin() as connection:
        Base.metadata.create_all(connection)

        # Supabase has these API roles; a local PostgreSQL instance may not.
        api_roles = connection.execute(
            text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        ).scalars().all()
        identifiers = connection.dialect.identifier_preparer

        for table in Base.metadata.sorted_tables:
            table_name = identifiers.format_table(table)
            connection.execute(
                text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
            )
            for role in api_roles:
                role_name = identifiers.quote(role)
                connection.execute(
                    text(f"REVOKE ALL ON TABLE {table_name} FROM {role_name}")
                )


if __name__ == "__main__":
    init_db()
    print("Database tables are ready.")
