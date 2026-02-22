from __future__ import annotations

from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import RedirectResponse

from aimg.admin.decorators import require_auth
from aimg.db.repos.jobs import JobRepo


@require_auth
async def dashboard_redirect(request: Request):
    return RedirectResponse("/admin/dashboard", status_code=302)


@require_auth
async def dashboard(request: Request):
    templates = request.app.state.templates
    db_pool = request.app.state.db_pool

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    job_repo = JobRepo(db_pool)
    stats = await job_repo.get_stats(date_from=today_start, date_to=now)
    stats_all = await job_repo.get_stats()

    return templates.TemplateResponse(request, "dashboard.html", {
        "stats_today": stats,
        "stats_all": stats_all,
    })
