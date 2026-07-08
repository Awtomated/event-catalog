"""Core data structures and base classes for the event catalog package.

The three dataclasses (EntityScope, EventDefinition, SuggestedTrigger) replace
the DB-backed models of the same name. They live entirely in memory — populated
at startup by each app's events.py file — so no migrations are needed to add or
change events.

BaseAction is the contract every pluggable action must implement. Register
subclass instances with `catalog.register_action(action_type, instance)`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Catalog dataclasses ────────────────────────────────────────────────────────

@dataclass
class SuggestedTrigger:
    """A pre-built trigger template shown as a one-click card in the UI.

    Replaces the SuggestedTrigger DB model. Registered alongside its parent
    EventDefinition inside register_event(..., suggestions=[...]).
    """
    slug: str                        # stable unique ID, e.g. 'sugg_project_started'
    label: str                       # card headline, e.g. 'When a project starts'
    event_name: str                  # dotted event slug this suggestion belongs to
    event_filters: dict = field(default_factory=dict)
    description: str = ''
    entity_source: str = 'context'   # 'context' | 'fixed'
    order: int = 0


@dataclass
class EventDefinition:
    """A named, triggerable event emitted by an app via publish().

    Replaces the EventDefinition DB model. Apps register these in events.py.
    The `name` field is the stable dotted slug used everywhere as the key
    (e.g. 'project.status_changed').
    """
    name: str                        # e.g. 'project.status_changed'
    scope: str                       # parent EntityScope slug, e.g. 'project'
    label: str                       # human-readable, e.g. 'Project Status Changed'
    signal_type: str                 # 'post_save' | 'post_tombstone' | 'm2m_changed' | 'periodic'
    description: str = ''
    available_filters: list[dict] = field(default_factory=list)
    context_schema: dict = field(default_factory=dict)
    suggestions: list[SuggestedTrigger] = field(default_factory=list)
    is_active: bool = True
    requires_editor_access: bool = False


@dataclass
class EntityScope:
    """Domain metadata wrapper for a Django model that can be an event source.

    Replaces the EntityScope DB model. Apps register these in events.py via
    catalog.register_scope(). The `model` string ('app_label.ModelName') is used
    for documentation and frontend display only — no ContentType FK required.
    """
    slug: str                        # e.g. 'project'
    model: str                       # e.g. 'project.Project'
    label: str                       # e.g. 'Project'
    verbose_name_plural: str = ''    # e.g. 'Projects'
    icon: str = ''                   # icon slug for frontend
    description: str = ''
    key_fields: list[dict] = field(default_factory=list)  # [{name, type, filterable}]
    order: int = 0


# ── Action contract ────────────────────────────────────────────────────────────

class BaseAction(ABC):
    """Abstract base class for all pluggable trigger actions.

    Subclass this in each service that needs to fire something when a
    WorkflowTrigger matches. Register the instance with:

        catalog.register_action('my_action_type', MyAction())

    The action_type string is stored on WorkflowTrigger.action_type in the DB,
    so it must be stable — never rename it without a data migration.

    Example
    -------
        class TemporalWorkflowAction(BaseAction):
            action_type = 'temporal_workflow'

            def fire(self, trigger, entity_id, context):
                org_wf_id = trigger.action_config['organisation_workflow_id']
                ...

            def get_config_schema(self):
                return {
                    'type': 'object',
                    'required': ['organisation_workflow_id'],
                    'properties': {
                        'organisation_workflow_id': {'type': 'integer'},
                    },
                }
    """
    action_type: str  # must be set on the subclass

    @abstractmethod
    def fire(self, trigger: Any, entity_id: str, context: dict) -> None:
        """Execute the action for one matched WorkflowTrigger.

        Raise an exception on failure — the caller (process_event_triggers)
        catches it, increments failed_items, and continues with other triggers.
        """

    def get_config_schema(self) -> dict:
        """Return a JSON Schema dict describing the action_config structure.

        Used by the API to tell the frontend what fields the action needs.
        Override when the action requires specific config.
        """
        return {}
