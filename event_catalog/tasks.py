"""Celery task that matches WorkflowTriggers against a published event.

This is the monolith-side counterpart of the Redis Stream consumer. Both paths
(CeleryTransport direct enqueue and RedisStreamTransport consumer) eventually
call this task with the same arguments.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.db import models
from django.utils import timezone

from .matcher import filters_match
from .models import WorkflowTrigger
from .registry import catalog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_event_triggers(
    self,
    event_name: str,
    org_id: str,
    entity_id: str,
    entity_scope: str,
    context: dict,
) -> dict:
    """Match active event triggers for (event_name, org_id) and fire each match.

    Args:
        event_name:   Dotted event slug, e.g. 'project.status_changed'.
        org_id:       Organisation identifier string.
        entity_id:    PK of the changed entity as a string.
        entity_scope: EntityScope slug, e.g. 'project'.
        context:      Event context dict from the signal handler.

    Returns:
        Summary dict with fired / skipped / failed counts.
    """
    triggers = WorkflowTrigger.objects.filter(
        trigger_type=WorkflowTrigger.TriggerType.EVENT,
        event_name=event_name,
        organisation_id=org_id,
        is_active=True,
    )

    fired = skipped = failed = 0

    for trigger in triggers:
        # Filter matching — pure function, no DB or network.
        if not filters_match(trigger.event_filters, context):
            skipped += 1
            continue

        try:
            action = catalog.get_action(trigger.action_type)
            action.fire(trigger, entity_id, context)

            # Atomic counter update — safe under concurrent task execution.
            WorkflowTrigger.objects.filter(pk=trigger.pk).update(
                fire_count=models.F('fire_count') + 1,
                last_fired_at=timezone.now(),
            )
            fired += 1

        except KeyError:
            logger.error(
                "process_event_triggers: unregistered action_type '%s' "
                "on trigger pk=%s — is the action registered in catalog_action.py?",
                trigger.action_type, trigger.pk,
            )
            failed += 1

        except Exception:
            logger.exception(
                "process_event_triggers: action '%s' raised for trigger pk=%s "
                "(event=%s org=%s entity=%s)",
                trigger.action_type, trigger.pk, event_name, org_id, entity_id,
            )
            failed += 1

    logger.info(
        "process_event_triggers: event=%s org=%s fired=%d skipped=%d failed=%d",
        event_name, org_id, fired, skipped, failed,
    )

    return {
        'event_name': event_name,
        'org_id': org_id,
        'entity_id': entity_id,
        'fired': fired,
        'skipped': skipped,
        'failed': failed,
    }
