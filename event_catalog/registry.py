"""Central registry for the event catalog package.

The `catalog` singleton at the bottom of this file is the single entry point
for all registrations. Apps import and call it from their events.py files:

    from event_catalog import catalog

    catalog.register_scope('project', model='project.Project', label='Project')
    catalog.register_event(scope='project', name='project.created', ...)
    catalog.register_action('temporal_workflow', TemporalWorkflowAction())
    catalog.register_filter_resolver('project.status_choices', lambda: [...])

Everything is collected here at startup (via apps.py autodiscovery) and served
in-memory — no DB reads for the catalog itself.
"""
from __future__ import annotations

from typing import Callable

from .base import BaseAction, EntityScope, EventDefinition, SuggestedTrigger


class EventRegistry:
    """Collects and serves event catalog registrations from all installed apps."""

    def __init__(self) -> None:
        self._scopes: dict[str, EntityScope] = {}
        # _events keyed by event name for O(1) lookup
        self._events: dict[str, EventDefinition] = {}
        self._actions: dict[str, BaseAction] = {}
        self._filter_resolvers: dict[str, Callable] = {}

    # ── Registration API ───────────────────────────────────────────────────────

    def register_scope(
        self,
        slug: str,
        *,
        model: str,
        label: str,
        verbose_name_plural: str = '',
        icon: str = '',
        description: str = '',
        key_fields: list[dict] | None = None,
        order: int = 0,
    ) -> None:
        """Register an entity scope.

        Args:
            slug: Unique short identifier, e.g. 'project'. Used as the key
                in the catalog response dict and stored on WorkflowTrigger rows.
            model: Django model path, e.g. 'project.Project'. Documentation only.
            label: Human-readable singular name shown in the UI.
        """
        if slug in self._scopes:
            raise ValueError(
                f"EntityScope '{slug}' is already registered. "
                f"Each scope slug must be unique across all apps."
            )
        self._scopes[slug] = EntityScope(
            slug=slug,
            model=model,
            label=label,
            verbose_name_plural=verbose_name_plural or f'{label}s',
            icon=icon,
            description=description,
            key_fields=key_fields or [],
            order=order,
        )

    def register_event(
        self,
        *,
        scope: str,
        name: str,
        label: str,
        signal_type: str,
        description: str = '',
        available_filters: list[dict] | None = None,
        context_schema: dict | None = None,
        suggestions: list[dict] | None = None,
        is_active: bool = True,
        requires_editor_access: bool = False,
    ) -> None:
        """Register an event definition under a scope.

        Args:
            scope: Slug of a previously registered EntityScope.
            name: Stable dotted slug, e.g. 'project.status_changed'. Never
                rename this — it is stored as a plain string on WorkflowTrigger.
            signal_type: One of 'post_save', 'post_tombstone', 'm2m_changed', 'periodic'.
            suggestions: List of dicts, each becoming a SuggestedTrigger. Required
                keys: slug, label. Optional: description, event_filters, entity_source, order.
        """
        if scope not in self._scopes:
            raise ValueError(
                f"Cannot register event '{name}': scope '{scope}' has not been registered. "
                f"Call register_scope('{scope}', ...) first."
            )
        if name in self._events:
            raise ValueError(
                f"Event '{name}' is already registered. Event names must be unique."
            )

        built_suggestions = [
            SuggestedTrigger(
                slug=s['slug'],
                label=s['label'],
                event_name=name,
                description=s.get('description', ''),
                event_filters=s.get('event_filters', {}),
                entity_source=s.get('entity_source', 'context'),
                order=s.get('order', 0),
            )
            for s in (suggestions or [])
        ]

        self._events[name] = EventDefinition(
            name=name,
            scope=scope,
            label=label,
            signal_type=signal_type,
            description=description,
            available_filters=available_filters or [],
            context_schema=context_schema or {},
            suggestions=built_suggestions,
            is_active=is_active,
            requires_editor_access=requires_editor_access,
        )

    def register_action(self, action_type: str, action_instance: BaseAction) -> None:
        """Register a BaseAction subclass instance under a string key.

        The action_type string is persisted on WorkflowTrigger rows in the DB.
        Never change it without a data migration.

        Args:
            action_type: Stable string key, e.g. 'temporal_workflow'.
            action_instance: An instantiated BaseAction subclass.
        """
        if not isinstance(action_instance, BaseAction):
            raise TypeError(
                f"action_instance must be a BaseAction subclass, "
                f"got {type(action_instance).__name__}."
            )
        if action_type in self._actions:
            raise ValueError(f"Action '{action_type}' is already registered.")
        self._actions[action_type] = action_instance

    def register_filter_resolver(self, source_key: str, resolver_fn: Callable) -> None:
        """Register a callable that returns dynamic filter options for a source key.

        The source_key matches the 'source' field on available_filters entries:

            available_filters=[
                {'key': 'new_status', 'type': 'choice', 'source': 'project.status_choices'},
            ]

        The resolver is called at serialization time and must return a list of
        {'value': ..., 'label': ...} dicts.

        Args:
            source_key: e.g. 'project.status_choices'
            resolver_fn: Zero-argument callable returning list[dict].
        """
        if source_key in self._filter_resolvers:
            raise ValueError(f"Filter resolver '{source_key}' is already registered.")
        self._filter_resolvers[source_key] = resolver_fn

    # ── Read API ───────────────────────────────────────────────────────────────

    def get_scopes(self) -> list[EntityScope]:
        """Return all registered scopes sorted by order then slug."""
        return sorted(self._scopes.values(), key=lambda s: (s.order, s.slug))

    def get_scope(self, slug: str) -> EntityScope | None:
        return self._scopes.get(slug)

    def get_events(
        self,
        *,
        scope: str | None = None,
        include_inactive: bool = False,
        editor_access: bool = False,
    ) -> list[EventDefinition]:
        """Return registered events, optionally filtered by scope.

        Args:
            scope: If given, only return events for this scope slug.
            include_inactive: Include events where is_active=False.
            editor_access: If False, exclude events requiring editor access.
        """
        events = self._events.values()

        if scope:
            events = (e for e in events if e.scope == scope)
        if not include_inactive:
            events = (e for e in events if e.is_active)
        if not editor_access:
            events = (e for e in events if not e.requires_editor_access)

        return sorted(events, key=lambda e: e.name)

    def get_event(self, name: str) -> EventDefinition | None:
        return self._events.get(name)

    def get_catalog(
        self,
        *,
        scope_slug: str | None = None,
        editor_access: bool = False,
        include_inactive: bool = False,
    ) -> dict:
        """Return the full grouped catalog dict consumed by EventCatalogView.

        Structure::

            {
                "project": {
                    "scope": {slug, model, label, icon, key_fields, ...},
                    "events": [...EventDefinition dicts...],
                    "suggested_triggers": [...SuggestedTrigger dicts...],
                },
                "task": { ... },
            }

        Args:
            scope_slug: If given, return only the entry for this scope.
        """
        scopes = self.get_scopes()
        if scope_slug:
            scopes = [s for s in scopes if s.slug == scope_slug]

        result = {}
        for scope in scopes:
            events = self.get_events(
                scope=scope.slug,
                include_inactive=include_inactive,
                editor_access=editor_access,
            )
            suggestions = sorted(
                [s for e in events for s in e.suggestions],
                key=lambda s: (s.order, s.label),
            )
            result[scope.slug] = {
                'scope': self._scope_to_dict(scope),
                'events': [self._event_to_dict(e) for e in events],
                'suggested_triggers': [self._suggestion_to_dict(s) for s in suggestions],
            }

        return result

    def get_action(self, action_type: str) -> BaseAction:
        """Return the registered action instance for a type key.

        Raises KeyError if the action_type is not registered.
        """
        try:
            return self._actions[action_type]
        except KeyError:
            registered = list(self._actions.keys())
            raise KeyError(
                f"No action registered for type '{action_type}'. "
                f"Registered types: {registered}"
            )

    def get_registered_action_types(self) -> list[dict]:
        """Return all registered action types with their config schemas."""
        return [
            {
                'action_type': action_type,
                'config_schema': instance.get_config_schema(),
            }
            for action_type, instance in self._actions.items()
        ]

    def resolve_filter_options(self, source_key: str) -> list[dict]:
        """Call the registered resolver for a source key and return options.

        Returns an empty list if no resolver is registered for the key.
        """
        resolver = self._filter_resolvers.get(source_key)
        if resolver is None:
            return []
        return resolver()

    def has_active_event(self, name: str) -> bool:
        """Return True if an active event with this name is registered.

        Used by publisher.publish() for early-exit before querying the DB.
        """
        event = self._events.get(name)
        return event is not None and event.is_active

    # ── Serialization helpers ──────────────────────────────────────────────────

    def _scope_to_dict(self, scope: EntityScope) -> dict:
        return {
            'slug': scope.slug,
            'model': scope.model,
            'label': scope.label,
            'verbose_name_plural': scope.verbose_name_plural,
            'icon': scope.icon,
            'description': scope.description,
            'key_fields': scope.key_fields,
        }

    def _event_to_dict(self, event: EventDefinition) -> dict:
        return {
            'name': event.name,
            'scope': event.scope,
            'label': event.label,
            'description': event.description,
            'signal_type': event.signal_type,
            'available_filters': self._resolve_filters(event.available_filters),
            'context_schema': event.context_schema,
            'is_active': event.is_active,
            'requires_editor_access': event.requires_editor_access,
        }

    def _suggestion_to_dict(self, s: SuggestedTrigger) -> dict:
        return {
            'id': s.slug,
            'label': s.label,
            'description': s.description,
            'event_name': s.event_name,
            'event_filters': s.event_filters,
            'entity_source': s.entity_source,
        }

    def _resolve_filters(self, available_filters: list[dict]) -> list[dict]:
        """Replace 'source' keys with live options from registered resolvers."""
        resolved = []
        for f in available_filters:
            entry = {k: v for k, v in f.items() if k != 'source'}
            source_key = f.get('source')
            if source_key:
                entry['options'] = self.resolve_filter_options(source_key)
            resolved.append(entry)
        return resolved


# ── Public singleton ───────────────────────────────────────────────────────────
# All apps import this and call registration methods on it.
catalog = EventRegistry()
