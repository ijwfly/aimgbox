from __future__ import annotations

import csv
import io
from datetime import date

from starlette.responses import Response

from aimg.db.models import Job

CSV_COLUMNS = [
    "id", "status", "job_type_id", "integration_id", "user_id",
    "credit_charged", "error_code", "created_at", "started_at", "completed_at",
]


def export_jobs_csv(jobs: list[Job]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    for job in jobs:
        writer.writerow([
            str(job.id),
            job.status,
            str(job.job_type_id),
            str(job.integration_id),
            str(job.user_id),
            job.credit_charged,
            job.error_code or "",
            job.created_at.isoformat(),
            job.started_at.isoformat() if job.started_at else "",
            job.completed_at.isoformat() if job.completed_at else "",
        ])

    content = output.getvalue()
    filename = f"jobs-{date.today().isoformat()}.csv"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
