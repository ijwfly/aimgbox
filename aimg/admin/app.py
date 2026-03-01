from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from aimg.admin.middleware import AdminSessionMiddleware
from aimg.admin.routes.api_keys import generate_key, revoke_key
from aimg.admin.routes.audit import audit_list
from aimg.admin.routes.auth import login_page, login_submit, logout
from aimg.admin.routes.dashboard import dashboard, dashboard_redirect
from aimg.admin.routes.integrations import (
    integration_create,
    integration_detail,
    integration_list,
    integration_new,
    integration_status,
    integration_update,
)
from aimg.admin.routes.job_types import (
    job_type_detail,
    job_type_list,
    job_type_provider_add,
    job_type_provider_remove,
    job_type_update,
)
from aimg.admin.routes.jobs import job_detail, job_export, job_list
from aimg.admin.routes.partners import (
    partner_create,
    partner_detail,
    partner_list,
    partner_new,
    partner_status,
)
from aimg.admin.routes.providers import (
    provider_create,
    provider_detail,
    provider_list,
    provider_new,
    provider_update,
)
from aimg.admin.routes.test_jobs import (
    test_job_create,
    test_job_fields,
    test_job_form,
    test_job_poll,
)
from aimg.admin.routes.users import user_credit_adjust, user_detail, user_list
from aimg.common.connections import create_db_pool, create_redis_client, create_s3_client
from aimg.common.settings import Settings

TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: Starlette):
    settings = app.state.settings
    app.state.db_pool = await create_db_pool(settings)
    app.state.redis = create_redis_client(settings)
    s3_cm = create_s3_client(settings)
    app.state.s3_client = await s3_cm.__aenter__()
    app.state._s3_cm = s3_cm
    yield
    await app.state._s3_cm.__aexit__(None, None, None)
    await app.state.db_pool.close()
    await app.state.redis.aclose()


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "admin"})


def create_admin_app(settings: Settings | None = None) -> Starlette:
    if settings is None:
        settings = Settings()

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/admin/health", health, methods=["GET"]),

        # Auth
        Route("/admin/login", login_page, methods=["GET"]),
        Route("/admin/login", login_submit, methods=["POST"]),
        Route("/admin/logout", logout, methods=["GET"]),

        # Dashboard
        Route("/admin/", dashboard_redirect, methods=["GET"]),
        Route("/admin/dashboard", dashboard, methods=["GET"]),

        # Partners
        Route("/admin/partners", partner_list, methods=["GET"]),
        Route("/admin/partners/new", partner_new, methods=["GET"]),
        Route("/admin/partners", partner_create, methods=["POST"]),
        Route("/admin/partners/{id:uuid}", partner_detail, methods=["GET"]),
        Route("/admin/partners/{id:uuid}/status", partner_status, methods=["POST"]),

        # Integrations
        Route("/admin/integrations", integration_list, methods=["GET"]),
        Route("/admin/integrations/new", integration_new, methods=["GET"]),
        Route("/admin/integrations", integration_create, methods=["POST"]),
        Route("/admin/integrations/{id:uuid}", integration_detail, methods=["GET"]),
        Route("/admin/integrations/{id:uuid}/update", integration_update, methods=["POST"]),
        Route("/admin/integrations/{id:uuid}/status", integration_status, methods=["POST"]),

        # API Keys
        Route("/admin/integrations/{id:uuid}/keys", generate_key, methods=["POST"]),
        Route("/admin/keys/{id:uuid}/revoke", revoke_key, methods=["POST"]),

        # Users
        Route("/admin/users", user_list, methods=["GET"]),
        Route("/admin/users/{id:uuid}", user_detail, methods=["GET"]),
        Route("/admin/users/{id:uuid}/credits", user_credit_adjust, methods=["POST"]),

        # Jobs
        Route("/admin/jobs", job_list, methods=["GET"]),
        Route("/admin/jobs/export", job_export, methods=["GET"]),
        Route("/admin/jobs/{id:uuid}", job_detail, methods=["GET"]),

        # Test Jobs
        Route("/admin/test-jobs", test_job_form, methods=["GET"]),
        Route("/admin/test-jobs", test_job_create, methods=["POST"]),
        Route("/admin/test-jobs/fields", test_job_fields, methods=["GET"]),
        Route("/admin/test-jobs/poll/{job_id}", test_job_poll, methods=["GET"]),

        # Job Types
        Route("/admin/job-types", job_type_list, methods=["GET"]),
        Route("/admin/job-types/{id:uuid}", job_type_detail, methods=["GET"]),
        Route("/admin/job-types/{id:uuid}/update", job_type_update, methods=["POST"]),
        Route("/admin/job-types/{id:uuid}/providers", job_type_provider_add, methods=["POST"]),
        Route(
            "/admin/job-types/{jt_id:uuid}/providers/{p_id:uuid}/remove",
            job_type_provider_remove,
            methods=["POST"],
        ),

        # Providers
        Route("/admin/providers", provider_list, methods=["GET"]),
        Route("/admin/providers/new", provider_new, methods=["GET"]),
        Route("/admin/providers", provider_create, methods=["POST"]),
        Route("/admin/providers/{id:uuid}", provider_detail, methods=["GET"]),
        Route("/admin/providers/{id:uuid}/update", provider_update, methods=["POST"]),

        # Audit
        Route("/admin/audit", audit_list, methods=["GET"]),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.settings = settings
    app.state.templates = templates
    app.add_middleware(AdminSessionMiddleware)

    # Use a Jinja2 context processor via TemplateResponse override
    _orig_template_response = templates.TemplateResponse

    def template_response_with_user(request, name, context=None, **kwargs):
        ctx = context or {}
        ctx.setdefault("admin_user", getattr(request.state, "admin_user", None))
        ctx.setdefault("request", request)
        return _orig_template_response(request, name, ctx, **kwargs)

    templates.TemplateResponse = template_response_with_user

    return app
