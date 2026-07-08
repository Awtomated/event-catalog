"""WorkflowTrigger — the only DB-backed model in this package.

All catalog data (EntityScope, EventDefinition, SuggestedTrigger) lives in the
in-memory registry populated by each app's events.py at startup. Only
user-created trigger configuration needs to be persisted in the database.

Key design decisions vs the original main-api model:
  - No FK to temporal_workflows.OrganisationWorkflow → action_type + action_config
  - No FK to EventDefinition (DB row) → event_name CharField (dotted slug)
  - No FK to EntityScope (DB row) → fixed_entity_scope_slug CharField
  - No FK to account.User → created_by_id CharField
  - organisation_id is a plain string — works with any project's org model
"""
from __future__ import annotations

from django.db import models
from django_extensions.db.models import TimeStampedModel


class WorkflowTrigger(TimeStampedModel):
    """A user-configured trigger that fires an action when an event matches.

    Two trigger types exist:
      EVENT    — fires when a named event is published and filter conditions match.
      SCHEDULE — fires on a cron schedule via an external scheduler (e.g. Temporal).

    The action to fire is identified by action_type (a registered BaseAction key)
    and action_config (action-specific JSON config, e.g. workflow ID).
    """

    class TriggerType(models.TextChoices):
        EVENT = 'event', 'Event'
        SCHEDULE = 'schedule', 'Schedule'

    class EntitySource(models.TextChoices):
        CONTEXT = 'context', 'Context'  # entity comes from the event payload
        FIXED = 'fixed', 'Fixed'        # entity is a specific pre-configured object

    # ── Organisation ───────────────────────────────────────────────────────────
    # Plain string — no FK to account.Organization. Allows this model to live in
    # any Django project without depending on a specific user/org model.
    organisation_id = models.CharField(max_length=255, db_index=True)

    # ── Trigger type ───────────────────────────────────────────────────────────
    trigger_type = models.CharField(
        max_length=20,
        choices=TriggerType.choices,
        default=TriggerType.EVENT,
    )

    # ── Event trigger fields (used when trigger_type = EVENT) ──────────────────
    # Dotted slug matching a registered EventDefinition, e.g. 'project.status_changed'.
    # Stored as a plain string — no FK to EventDefinition because the catalog is
    # now in-memory. Validated against the registry in the serializer.
    event_name = models.CharField(max_length=100, blank=True)

    # AND-logic filter conditions evaluated against the event context dict.
    # Empty dict = always fires. See matcher.filters_match() for supported formats.
    event_filters = models.JSONField(default=dict, blank=True)

    # ── Entity resolution ──────────────────────────────────────────────────────
    entity_source = models.CharField(
        max_length=20,
        choices=EntitySource.choices,
        default=EntitySource.CONTEXT,
    )
    # Used when entity_source = FIXED. Slug of a registered EntityScope.
    fixed_entity_scope_slug = models.CharField(max_length=50, blank=True)
    # PK of the fixed entity as a string.
    fixed_entity_id = models.CharField(max_length=255, blank=True)

    # ── Action ─────────────────────────────────────────────────────────────────
    # Registered action type key, e.g. 'temporal_workflow', 'webhook'.
    # Must match a BaseAction subclass registered via catalog.register_action().
    # Never rename this value without a data migration.
    action_type = models.CharField(max_length=50)

    # Action-specific configuration. Schema depends on action_type.
    # e.g. {'organisation_workflow_id': 42} for temporal_workflow action.
    # e.g. {'url': 'https://...', 'secret': '...'} for webhook action.
    action_config = models.JSONField(default=dict, blank=True)

    # ── Schedule trigger fields (used when trigger_type = SCHEDULE) ────────────
    cron_expression = models.CharField(max_length=100, blank=True)
    schedule_timezone = models.CharField(max_length=100, default='UTC')
    # ID assigned by the external scheduler (e.g. Temporal) for management.
    temporal_schedule_id = models.CharField(max_length=255, blank=True)

    # ── State ──────────────────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)

    # Updated atomically with F('fire_count') + 1 to avoid race conditions.
    fire_count = models.PositiveIntegerField(default=0)
    last_fired_at = models.DateTimeField(null=True, blank=True)

    # User who created this trigger. Plain string (no FK) so the model works
    # in any project. Store str(user.id) or user.email — caller's choice.
    created_by_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            # Primary lookup: find active event triggers for an org + event pair.
            models.Index(
                fields=['organisation_id', 'event_name', 'is_active'],
                name='ec_trigger_org_event_idx',
            ),
            # Secondary lookup: find all triggers for an org (list view).
            models.Index(
                fields=['organisation_id', 'trigger_type'],
                name='ec_trigger_org_type_idx',
            ),
        ]

    def __str__(self) -> str:
        if self.trigger_type == self.TriggerType.EVENT:
            return (
                f'{self.event_name} → {self.action_type}'
                f' (org:{self.organisation_id})'
            )
        return (
            f'schedule:{self.cron_expression} → {self.action_type}'
            f' (org:{self.organisation_id})'
        )
