import asyncio

from aimg.common.connections import create_db_pool
from aimg.common.settings import Settings
from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.users import UserRepo


async def run_reconcile() -> None:
    settings = Settings()
    db_pool = await create_db_pool(settings)

    try:
        user_repo = UserRepo(db_pool)
        ct_repo = CreditTransactionRepo(db_pool)

        users = await user_repo.list_all()
        latest = await ct_repo.get_latest_balances()

        # Build lookup: (user_id, credit_type) -> balance_after
        balance_map: dict[tuple, int] = {}
        for row in latest:
            key = (row["user_id"], row["credit_type"])
            balance_map[key] = row["balance_after"]

        mismatches = 0
        for user in users:
            expected_free = balance_map.get((user.id, "free"))
            expected_paid = balance_map.get((user.id, "paid"))

            free_ok = expected_free is None or user.free_credits == expected_free
            paid_ok = expected_paid is None or user.paid_credits == expected_paid

            if not free_ok or not paid_ok:
                mismatches += 1
                print(
                    f"MISMATCH user={user.id}: "
                    f"free={user.free_credits} (expected {expected_free}), "
                    f"paid={user.paid_credits} (expected {expected_paid})"
                )
                # Auto-fix
                new_free = expected_free if expected_free is not None else user.free_credits
                new_paid = expected_paid if expected_paid is not None else user.paid_credits
                await user_repo.force_set_credits(user.id, new_free, new_paid)
                print(f"  FIXED -> free={new_free}, paid={new_paid}")

        if mismatches == 0:
            print("All balances are consistent.")
        else:
            print(f"\nFixed {mismatches} mismatched user(s).")
    finally:
        await db_pool.close()


def main() -> None:
    asyncio.run(run_reconcile())
