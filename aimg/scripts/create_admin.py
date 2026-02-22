import argparse
import asyncio
import sys

from aimg.admin.auth import hash_password
from aimg.common.connections import create_db_pool
from aimg.common.settings import Settings
from aimg.db.repos.admin_users import AdminUserRepo


async def run_create_admin(username: str, password: str, role: str) -> None:
    settings = Settings()
    db_pool = await create_db_pool(settings)

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
    args = parser.parse_args(sys.argv[2:])

    asyncio.run(run_create_admin(args.username, args.password, args.role))
