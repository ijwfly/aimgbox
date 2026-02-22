import csv
import io
from datetime import UTC, datetime
from uuid import uuid4

from aimg.admin.csv_export import export_jobs_csv
from aimg.db.models import Job


def _make_job(**overrides):
    defaults = {
        "id": uuid4(),
        "integration_id": uuid4(),
        "user_id": uuid4(),
        "job_type_id": uuid4(),
        "status": "succeeded",
        "input_data": {},
        "output_data": None,
        "provider_id": None,
        "credit_charged": 1,
        "error_code": None,
        "error_message": None,
        "provider_job_id": None,
        "attempts": 1,
        "language": "en",
        "idempotency_key": None,
        "started_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        "completed_at": datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC),
        "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_export_empty():
    response = export_jobs_csv([])
    assert "text/csv" in response.media_type
    assert "attachment" in response.headers["content-disposition"]


def test_export_with_jobs():
    jobs = [_make_job(), _make_job(status="failed", error_code="TIMEOUT")]
    response = export_jobs_csv(jobs)

    body = response.body.decode()
    reader = csv.reader(io.StringIO(body))
    rows = list(reader)
    assert rows[0][0] == "id"  # header
    assert len(rows) == 3  # header + 2 jobs
    assert rows[1][1] == "succeeded"
    assert rows[2][1] == "failed"
    assert rows[2][6] == "TIMEOUT"


def test_export_no_completed():
    job = _make_job(started_at=None, completed_at=None)
    response = export_jobs_csv([job])

    body = response.body.decode()
    reader = csv.reader(io.StringIO(body))
    rows = list(reader)
    assert rows[1][8] == ""  # started_at
    assert rows[1][9] == ""  # completed_at
