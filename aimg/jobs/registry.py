import importlib
import pkgutil
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class HandlerInfo:
    slug: str
    name: str
    description: str
    handler_fn: Callable
    input_model: type
    output_model: type


class JobRegistry:
    _handlers: dict[str, HandlerInfo] = {}

    @classmethod
    def register(cls, info: HandlerInfo) -> None:
        cls._handlers[info.slug] = info

    @classmethod
    def get(cls, slug: str) -> HandlerInfo | None:
        return cls._handlers.get(slug)

    @classmethod
    def all(cls) -> dict[str, HandlerInfo]:
        return dict(cls._handlers)


def job_handler(
    slug: str,
    name: str,
    description: str = "",
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        # Use get_type_hints to resolve string annotations (from __future__)
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}

        ctx_type = hints.get("ctx")
        input_model: Any = None
        output_model: Any = None
        if ctx_type and hasattr(ctx_type, "__args__") and ctx_type.__args__:
            input_model = ctx_type.__args__[0]
            if len(ctx_type.__args__) > 1:
                output_model = ctx_type.__args__[1]

        return_type = hints.get("return")
        if return_type and output_model is None:
            output_model = return_type

        info = HandlerInfo(
            slug=slug,
            name=name,
            description=description,
            handler_fn=fn,
            input_model=input_model,
            output_model=output_model,
        )
        JobRegistry.register(info)
        fn._handler_info = info
        return fn

    return decorator


def discover_handlers() -> None:
    import aimg.jobs.handlers as handlers_pkg

    for importer, modname, ispkg in pkgutil.iter_modules(handlers_pkg.__path__):
        importlib.import_module(f"aimg.jobs.handlers.{modname}")
