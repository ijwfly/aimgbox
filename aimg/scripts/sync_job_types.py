import asyncio

from aimg.common.connections import create_db_pool
from aimg.common.settings import Settings
from aimg.db.repos.job_types import JobTypeRepo
from aimg.jobs.registry import JobRegistry, discover_handlers


async def run_sync() -> None:
    settings = Settings()
    db_pool = await create_db_pool(settings)

    try:
        discover_handlers()
        jt_repo = JobTypeRepo(db_pool)

        for slug, info in JobRegistry.all().items():
            input_schema = {}
            output_schema = {}

            if info.input_model and hasattr(info.input_model, "model_json_schema"):
                input_schema = info.input_model.model_json_schema()
            if info.output_model and hasattr(info.output_model, "model_json_schema"):
                output_schema = info.output_model.model_json_schema()

            jt = await jt_repo.upsert(
                slug=slug,
                name=info.name,
                description=info.description,
                input_schema=input_schema,
                output_schema=output_schema,
            )
            print(f"Synced: {jt.slug} (id={jt.id})")

        print("Sync complete")
    finally:
        await db_pool.close()


def main() -> None:
    asyncio.run(run_sync())
