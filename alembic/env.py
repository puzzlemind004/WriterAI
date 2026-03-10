import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Ajoute le projet au path pour importer les modèles
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.storage.models import Base  # noqa: E402
from config.settings import settings    # noqa: E402

# Alembic Config
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata pour l'autogenerate
target_metadata = Base.metadata

# L'URL est lue directement depuis settings dans run_async_migrations
# (on évite set_main_option car configparser interprète % comme interpolation)


def run_migrations_offline() -> None:
    """Mode offline : génère le SQL sans connexion DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Mode online : connexion async via asyncpg."""
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        settings.database_url,
        connect_args={"ssl": "disable"},
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
