from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ApiResponse[T](BaseModel):
    request_id: str
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
