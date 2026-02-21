from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class InputFile:
    file_id: UUID
    data: bytes
    content_type: str
    original_filename: str | None
    size_bytes: int


@dataclass
class OutputFile:
    data: bytes
    content_type: str
    filename: str | None = None


@dataclass
class FileConstraints:
    max_size_mb: float = 20.0
    formats: list[str] = field(default_factory=lambda: ["png", "jpg", "webp"])

    def validate(self, content_type: str, size_bytes: int) -> list[str]:
        errors = []
        max_bytes = int(self.max_size_mb * 1024 * 1024)
        if size_bytes > max_bytes:
            errors.append(
                f"File size {size_bytes} exceeds limit {max_bytes} bytes"
            )
        # Extract format from content_type, e.g. "image/png" -> "png", "image/jpeg" -> "jpg"
        fmt = content_type.rsplit("/", 1)[-1] if "/" in content_type else content_type
        if fmt == "jpeg":
            fmt = "jpg"
        if fmt not in self.formats:
            errors.append(
                f"Format '{fmt}' not allowed. Allowed: {self.formats}"
            )
        return errors
