import asyncio
import os
from pathlib import Path
import aiosqlite


MIGRATIONS_DIR = Path("migrations")
DB_DIR = Path("db")


async def _apply_migrations_to_db(db_path: Path, migrations: list[Path]) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()

        async with db.execute("SELECT id FROM _migrations") as cursor:
            applied = {row[0] for row in await cursor.fetchall()}

        for migration in migrations:
            migration_id = migration.name
            if migration_id in applied:
                continue

            sql = migration.read_text(encoding="utf-8")
            if sql.strip():
                await db.executescript(sql)
            await db.execute("INSERT INTO _migrations (id) VALUES (?)", (migration_id,))
            await db.commit()


async def run_migrations() -> None:
    if not MIGRATIONS_DIR.exists():
        return

    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        return

    if not DB_DIR.exists():
        DB_DIR.mkdir(parents=True, exist_ok=True)

    db_files = sorted(DB_DIR.glob("*.sqlite"))
    if not db_files:
        return

    for db_path in db_files:
        await _apply_migrations_to_db(db_path, migrations)


def run_migrations_sync() -> None:
    asyncio.run(run_migrations())
