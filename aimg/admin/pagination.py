from __future__ import annotations

import math


def get_page_info(
    page: int,
    total: int,
    per_page: int = 50,
) -> dict:
    if page < 1:
        page = 1
    total_pages = max(1, math.ceil(total / per_page))
    if page > total_pages:
        page = total_pages
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "offset": (page - 1) * per_page,
    }
