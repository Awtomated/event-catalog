"""Transport loader — resolves and caches the configured transport instance.

Import get_transport() in publisher.py only. Everything else uses publish().
"""
from __future__ import annotations

from .base import BaseTransport

# Module-level cache. Reset to None in tests that need a different transport.
_transport_instance: BaseTransport | None = None


def get_transport() -> BaseTransport:
    """Return the transport instance configured in settings.EVENT_CATALOG.

    The instance is created once and reused for the lifetime of the process.
    Default transport is CeleryTransport if settings are absent.
    """
    global _transport_instance
    if _transport_instance is None:
        _transport_instance = _load_transport()
    return _transport_instance


def _load_transport() -> BaseTransport:
    from importlib import import_module

    from django.conf import settings

    cfg = getattr(settings, 'EVENT_CATALOG', {})
    transport_path = cfg.get(
        'TRANSPORT',
        'event_catalog.transport.celery.CeleryTransport',
    )

    module_path, class_name = transport_path.rsplit('.', 1)
    module = import_module(module_path)
    transport_class = getattr(module, class_name)

    if not (isinstance(transport_class, type) and issubclass(transport_class, BaseTransport)):
        raise TypeError(
            f"EVENT_CATALOG['TRANSPORT'] must point to a BaseTransport subclass, "
            f"got {transport_class!r}."
        )

    return transport_class()


def reset_transport() -> None:
    """Clear the cached transport instance. Call this in test tearDown()."""
    global _transport_instance
    _transport_instance = None
