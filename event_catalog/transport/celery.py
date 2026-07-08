"""CeleryTransport — in-process transport for main-api.

Used when the service that emits events also owns the WorkflowTrigger table.
Performs an early-exit DB check before enqueueing the Celery task so that
events with no matching triggers never touch the task queue.
"""
from __future__ import annotations

from .base import BaseTransport


class CeleryTransport(BaseTransport):
    """Deliver events via a Celery task enqueued directly in-process.

    Requires the full install extra (Django + Celery + DB access).

    Settings
    --------
    No additional settings beyond 'TRANSPORT' are required.
    """

    def send(
        self,
        event_name: str,
        org_id: str,
        entity_id: str,
        entity_scope: str,
        context: dict,
    ) -> None:
        # Lazy imports keep this module importable before Django is fully set up.
        from event_catalog.models import WorkflowTrigger
        from event_catalog.tasks import process_event_triggers

        # Early exit: skip the task queue entirely if no active triggers exist
        # for this event + org combination. This is the same guard that was in
        # the original publisher.py and keeps the queue clean.
        has_triggers = WorkflowTrigger.objects.filter(
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name=event_name,
            organisation_id=org_id,
            is_active=True,
        ).exists()

        if not has_triggers:
            return

        process_event_triggers.delay(
            event_name,
            org_id,
            entity_id,
            entity_scope,
            context,
        )
