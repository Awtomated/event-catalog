"""Single entry point for emitting events from signal handlers.

Usage
-----
    from event_catalog import publish

    # Inside a post_save signal handler (already inside a transaction):
    publish(
        event_name='project.status_changed',
        org_id=str(instance.organisation_id),
        entity_id=str(instance.id),
        entity_scope='project',
        context={
            'new_status': instance.status,
            'old_status': old_status,
            'project_id': str(instance.id),
            'org_id': str(instance.organisation_id),
        },
    )

The call is a no-op if the event name is not registered in the catalog —
no transport is touched, no DB query is made.

The transport.send() call is deferred to transaction.on_commit() so that:
  - The DB row (project, task, file, etc.) is guaranteed to be visible to
    other connections before the matcher reads it.
  - If the transaction rolls back, the event is silently dropped — correct
    behaviour since the triggering change never happened.
"""
from __future__ import annotations

import logging

from .registry import catalog
from .transport import get_transport

logger = logging.getLogger(__name__)


def publish(
    event_name: str,
    org_id: str,
    entity_id: str,
    entity_scope: str,
    context: dict,
) -> None:
    """Emit an event to registered trigger matchers.

    Must be called from within an active Django DB transaction (i.e. inside
    a signal handler or an atomic() block). The send is deferred to
    transaction.on_commit() automatically.

    Args:
        event_name:   Dotted slug matching a registered EventDefinition,
                      e.g. 'project.status_changed'.
        org_id:       Organisation identifier as a string.
        entity_id:    PK of the entity that changed, as a string.
        entity_scope: Slug of the registered EntityScope, e.g. 'project'.
        context:      Dict of event-specific data (status values, flags, etc.).
                      Must be JSON-serialisable.
    """
    from django.db import transaction

    # Skip entirely if the event is not registered or is inactive.
    # This prevents any transport or DB work for unknown event names.
    if not catalog.has_active_event(event_name):
        logger.debug("publish: skipping unregistered or inactive event '%s'", event_name)
        return

    transport = get_transport()

    # Capture all args in the closure — avoids late-binding bugs with loops.
    _name = event_name
    _org = str(org_id)
    _entity = str(entity_id)
    _scope = entity_scope
    _ctx = context

    def _send() -> None:
        try:
            transport.send(_name, _org, _entity, _scope, _ctx)
        except Exception:
            logger.exception(
                "publish: transport failed for event '%s' org=%s entity=%s",
                _name, _org, _entity,
            )

    transaction.on_commit(_send)
