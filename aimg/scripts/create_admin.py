import argparse
import asyncio
import os
import sys

import asyncpg

from aimg.admin.auth import hash_password
from aimg.db.repos.admin_users import AdminUserRepo

DEFAULT_DSN = "postgresql://aimg:aimg@localhost:5432/aimg"


async def run_create_admin(dsn: str, username: str, password: str, role: str) -> None:
    db_pool = await asyncpg.create_pool(dsn=dsn)

    try:
        repo = AdminUserRepo(db_pool)
        existing = await repo.get_by_username(username)
        if existing:
            print(f"Admin user '{username}' already exists (id={existing.id})")
            return

        pw_hash = hash_password(password)
        user = await repo.create(username, pw_hash, role)
        print(f"Admin user created: {user.username} (role={user.role}, id={user.id})")
    finally:
        await db_pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create admin user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="admin", choices=["super_admin", "admin", "viewer"])
    parser.add_argument("--database-url", default=None, help="PostgreSQL DSN")
    args = parser.parse_args(sys.argv[2:])

    dsn = args.database_url or os.environ.get("AIMG_DATABASE_URL", DEFAULT_DSN)
    asyncio.run(run_create_admin(dsn, args.username, args.password, args.role))
