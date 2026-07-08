"""Pure filter-matching logic for event triggers.

No Django imports — this module is intentionally framework-free so it
can be copied verbatim into the Event Catalog microservice.

Usage
-----
    from event_catalog.matcher import filters_match

    fired = filters_match(trigger.event_filters, event_context)
"""
from typing import Any


def filters_match(event_filters: dict, context: dict) -> bool:
    """Return True if all filter conditions are satisfied by the context.

    Empty filters always match — the trigger fires on every occurrence
    of the event.

    Each key in ``event_filters`` is checked against the same key in
    ``context``. A missing context key is treated as a non-match.

    Supported value formats
    -----------------------
    Simple equality::

        {"new_status": "in_progress"}

    Operator dict::

        {"new_status": {"op": "eq",      "value": "in_progress"}}
        {"new_status": {"op": "neq",     "value": "todo"}}
        {"new_status": {"op": "in",      "value": ["done", "closed"]}}
        {"new_status": {"op": "not_in",  "value": ["todo", "archive"]}}
        {"old_status": {"op": "contains","value": "progress"}}

    When a plain (non-dict) value is given, ``eq`` is assumed.
    """
    if not event_filters:
        return True

    for field, condition in event_filters.items():
        actual = context.get(field)

        if isinstance(condition, dict):
            op = condition.get('op', 'eq')
            expected = condition.get('value')
        else:
            op = 'eq'
            expected = condition

        if not _check(op, actual, expected):
            return False

    return True


def _check(op: str, actual: Any, expected: Any) -> bool:
    if op == 'eq':
        return actual == expected
    if op == 'neq':
        return actual != expected
    if op == 'in':
        return actual in expected
    if op == 'not_in':
        return actual not in expected
    if op == 'contains':
        return isinstance(actual, str) and expected in actual
    return False
