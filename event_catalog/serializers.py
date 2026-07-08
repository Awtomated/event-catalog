"""DRF serializers for WorkflowTrigger CRUD and the event catalog API.

Read and write serializers are kept separate so the API always returns a rich
read representation (with inlined event definition and action schema from the
registry) regardless of what was sent in the write payload.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import WorkflowTrigger
from .registry import catalog


# ── Catalog read serializers ───────────────────────────────────────────────────

class EntityScopeSerializer(serializers.Serializer):
    """Read-only representation of a registered EntityScope."""
    slug = serializers.CharField()
    model = serializers.CharField()
    label = serializers.CharField()
    verbose_name_plural = serializers.CharField()
    icon = serializers.CharField()
    description = serializers.CharField()
    key_fields = serializers.ListField()


class SuggestedTriggerSerializer(serializers.Serializer):
    """Read-only representation of a SuggestedTrigger (one-click card)."""
    id = serializers.CharField()           # slug exposed as id
    label = serializers.CharField()
    description = serializers.CharField()
    event_name = serializers.CharField()
    event_filters = serializers.DictField()
    entity_source = serializers.CharField()


class EventDefinitionSerializer(serializers.Serializer):
    """Read-only representation of a registered EventDefinition."""
    name = serializers.CharField()
    scope = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    signal_type = serializers.CharField()
    available_filters = serializers.ListField()  # already resolved by registry
    context_schema = serializers.DictField()
    is_active = serializers.BooleanField()
    requires_editor_access = serializers.BooleanField()


class EventDefinitionSummarySerializer(serializers.Serializer):
    """Minimal EventDefinition nested inside trigger read responses."""
    name = serializers.CharField()
    label = serializers.CharField()
    signal_type = serializers.CharField()
    is_active = serializers.BooleanField()


# ── Trigger serializers ────────────────────────────────────────────────────────

class WorkflowTriggerReadSerializer(serializers.ModelSerializer):
    """Full read representation of a WorkflowTrigger.

    Inlines the EventDefinition summary and EntityScope from the in-memory
    registry so the frontend has everything it needs in one response.
    """
    event_definition = serializers.SerializerMethodField()
    fixed_entity_scope = serializers.SerializerMethodField()
    action_config_schema = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowTrigger
        fields = [
            'id',
            'organisation_id',
            'trigger_type',
            # event trigger
            'event_name',
            'event_definition',
            'event_filters',
            # entity resolution
            'entity_source',
            'fixed_entity_scope_slug',
            'fixed_entity_id',
            'fixed_entity_scope',
            # action
            'action_type',
            'action_config',
            'action_config_schema',
            # schedule trigger
            'cron_expression',
            'schedule_timezone',
            'temporal_schedule_id',
            # state
            'is_active',
            'fire_count',
            'last_fired_at',
            'created_by_id',
            'created',
            'modified',
        ]
        read_only_fields = fields

    def get_event_definition(self, obj: WorkflowTrigger) -> dict | None:
        if not obj.event_name:
            return None
        event = catalog.get_event(obj.event_name)
        if event is None:
            # Event was deregistered after trigger was created — surface the name.
            return {'name': obj.event_name, 'label': obj.event_name,
                    'signal_type': '', 'is_active': False}
        return EventDefinitionSummarySerializer(event).data

    def get_fixed_entity_scope(self, obj: WorkflowTrigger) -> dict | None:
        if not obj.fixed_entity_scope_slug:
            return None
        scope = catalog.get_scope(obj.fixed_entity_scope_slug)
        if scope is None:
            return {'slug': obj.fixed_entity_scope_slug, 'label': obj.fixed_entity_scope_slug}
        return {'slug': scope.slug, 'label': scope.label, 'icon': scope.icon}

    def get_action_config_schema(self, obj: WorkflowTrigger) -> dict:
        try:
            return catalog.get_action(obj.action_type).get_config_schema()
        except KeyError:
            return {}


class WorkflowTriggerWriteSerializer(serializers.ModelSerializer):
    """Write serializer for creating and updating WorkflowTrigger instances.

    Validates event_name against the registry (must be a registered active event)
    and action_type against registered actions. organisation_id and created_by_id
    are injected by the view — not accepted from request data.
    """

    class Meta:
        model = WorkflowTrigger
        fields = [
            'trigger_type',
            'event_name',
            'event_filters',
            'entity_source',
            'fixed_entity_scope_slug',
            'fixed_entity_id',
            'action_type',
            'action_config',
            'cron_expression',
            'schedule_timezone',
            'is_active',
        ]

    def validate_event_name(self, value: str) -> str:
        if value and not catalog.has_active_event(value):
            raise serializers.ValidationError(
                f"'{value}' is not a registered active event."
            )
        return value

    def validate_action_type(self, value: str) -> str:
        try:
            catalog.get_action(value)
        except KeyError:
            registered = [t['action_type'] for t in catalog.get_registered_action_types()]
            raise serializers.ValidationError(
                f"'{value}' is not a registered action type. "
                f"Registered types: {registered or ['(none yet)']}"
            )
        return value

    def validate(self, attrs: dict) -> dict:
        trigger_type = attrs.get('trigger_type', WorkflowTrigger.TriggerType.EVENT)

        if trigger_type == WorkflowTrigger.TriggerType.EVENT:
            if not attrs.get('event_name'):
                raise serializers.ValidationError(
                    {'event_name': 'This field is required for event triggers.'}
                )

        elif trigger_type == WorkflowTrigger.TriggerType.SCHEDULE:
            if not attrs.get('cron_expression'):
                raise serializers.ValidationError(
                    {'cron_expression': 'This field is required for schedule triggers.'}
                )

        entity_source = attrs.get('entity_source', WorkflowTrigger.EntitySource.CONTEXT)
        if entity_source == WorkflowTrigger.EntitySource.FIXED:
            errors = {}
            if not attrs.get('fixed_entity_scope_slug'):
                errors['fixed_entity_scope_slug'] = (
                    'Required when entity_source is "fixed".'
                )
            if not attrs.get('fixed_entity_id'):
                errors['fixed_entity_id'] = (
                    'Required when entity_source is "fixed".'
                )
            if errors:
                raise serializers.ValidationError(errors)

        return attrs
