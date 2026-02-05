"""Quick database check script."""

import asyncio
import os
import ssl
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


DATABASE_URL = "postgresql+asyncpg://postgres:eehVvqlgriwncHLOlughMeacVrySHtTj@caboose.proxy.rlwy.net:46468/railway"


async def check():
    print("Connecting to Railway PostgreSQL...")

    # Create SSL context for Railway
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"ssl": ssl_context}
    )

    async with engine.connect() as conn:
        # Check tables
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]

        print(f"\nTables found: {len(tables)}")
        for t in tables:
            # Count rows
            count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {t}"))
            count = count_result.scalar()
            print(f"  - {t}: {count} rows")

    await engine.dispose()
    print("\nDatabase connection OK!")


if __name__ == "__main__":
    asyncio.run(check())
