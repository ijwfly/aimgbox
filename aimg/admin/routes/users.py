from __future__ import annotations

from uuid import UUID

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.audit import log_action
from aimg.admin.decorators import require_auth, require_role
from aimg.admin.pagination import get_page_info
from aimg.db.repos.credit_transactions import CreditTransactionRepo
from aimg.db.repos.users import UserRepo


@require_auth
async def user_list(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    repo = UserRepo(db_pool)

    page = int(request.query_params.get("page", 1))
    query = request.query_params.get("q", "").strip()
    integration_id_str = request.query_params.get("integration_id")
    integration_id = UUID(integration_id_str) if integration_id_str else None

    total = await repo.count(query=query or None, integration_id=integration_id)
    page_info = get_page_info(page, total)
    users = await repo.search(
        query=query or None,
        integration_id=integration_id,
        limit=page_info["per_page"],
        offset=page_info["offset"],
    )

    ctx = {
        "users": users,
        "page_info": page_info,
        "search_query": query,
        "filter_integration_id": integration_id_str or "",
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "users/_rows.html", ctx)
    return templates.TemplateResponse(request, "users/list.html", ctx)


@require_auth
async def user_detail(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    user_id = UUID(str(request.path_params["id"]))

    user_repo = UserRepo(db_pool)
    user = await user_repo.get_by_id(user_id)
    if not user:
        return templates.TemplateResponse(
            request, "users/list.html",
            {"users": [], "page_info": get_page_info(1, 0),
             "search_query": "", "flash_error": "User not found"},
            status_code=404,
        )

    ct_repo = CreditTransactionRepo(db_pool)
    transactions = await ct_repo.list_by_user(user_id, limit=50)

    return templates.TemplateResponse(request, "users/detail.html", {
        "user": user,
        "transactions": transactions,
    })


@require_role("super_admin", "admin")
async def user_credit_adjust(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool
    user_id = UUID(str(request.path_params["id"]))

    form = await request.form()
    amount = int(form.get("amount", 0))
    credit_type = form.get("credit_type", "free")
    comment = form.get("comment", "").strip()

    if not comment:
        user = await UserRepo(db_pool).get_by_id(user_id)
        transactions = await CreditTransactionRepo(db_pool).list_by_user(user_id, limit=50)
        return templates.TemplateResponse(
            request, "users/detail.html",
            {"user": user, "transactions": transactions,
             "flash_error": "Comment is required for credit adjustments"},
            status_code=400,
        )

    if amount == 0:
        return RedirectResponse(f"/admin/users/{user_id}", status_code=302)

    admin_user = request.state.admin_user
    admin_user_id = UUID(admin_user["id"])

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            user_repo = UserRepo(db_pool)
            ct_repo = CreditTransactionRepo(db_pool)

            if credit_type == "free":
                ok = await user_repo.update_credits(
                    user_id, free_credits_delta=amount, paid_credits_delta=0, conn=conn
                )
            else:
                ok = await user_repo.update_credits(
                    user_id, free_credits_delta=0, paid_credits_delta=amount, conn=conn
                )

            if not ok:
                user = await user_repo.get_by_id(user_id, conn=conn)
                transactions = await ct_repo.list_by_user(user_id, limit=50, conn=conn)
                return templates.TemplateResponse(
                    request, "users/detail.html",
                    {"user": user, "transactions": transactions,
                     "flash_error": "Insufficient credits for negative adjustment"},
                    status_code=400,
                )

            user = await user_repo.get_by_id(user_id, conn=conn)
            balance_after = user.free_credits if credit_type == "free" else user.paid_credits

            await ct_repo.create(
                user_id=user_id,
                amount=amount,
                credit_type=credit_type,
                reason="admin_adjustment",
                balance_after=balance_after,
                admin_user_id=admin_user_id,
                comment=comment,
                conn=conn,
            )

    await log_action(
        request, "credits.adjust", "user", user_id,
        {"amount": amount, "credit_type": credit_type, "comment": comment},
    )

    return RedirectResponse(f"/admin/users/{user_id}", status_code=302)
