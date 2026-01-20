# migrations/env.py
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

config = context.config

# Prefer DATABASE_URL from the environment (avoid importing app config)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Railway uses postgres:// but SQLAlchemy 1.4+ requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(f"Only Postgres is supported. Got: {DATABASE_URL}")

if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
elif not config.get_main_option("sqlalchemy.url"):
    # Fail if no URL is available (neither in env nor ini)
    raise RuntimeError("DATABASE_URL is not set and sqlalchemy.url is empty; cannot run offline migrations.")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
