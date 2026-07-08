"""Abstract base class for event transports.

A transport is responsible for delivering a published event to wherever the
matcher runs. Two implementations ship with this package:

    CeleryTransport     — in-process, for services that own the WorkflowTrigger
                          table (e.g. main-api). Enqueues a Celery task directly.

    RedisStreamTransport — cross-service, for services that have a separate DB
                           (e.g. drive-ms). Writes the event to a Redis Stream;
                           main-api's consumer picks it up and enqueues the task.

Configure which transport to use in settings:

    EVENT_CATALOG = {
        'TRANSPORT': 'event_catalog.transport.celery.CeleryTransport',
    }
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTransport(ABC):
    """Contract every transport must implement."""

    @abstractmethod
    def send(
        self,
        event_name: str,
        org_id: str,
        entity_id: str,
        entity_scope: str,
        context: dict,
    ) -> None:
        """Deliver the event to the matcher.

        Called from inside a transaction.on_commit() callback, so the DB is
        guaranteed to be committed before this runs.

        Raise an exception on unrecoverable failure — the publisher does not
        retry; callers should rely on transport-level guarantees (e.g. Redis
        persistence, Celery retry policy).
        """
