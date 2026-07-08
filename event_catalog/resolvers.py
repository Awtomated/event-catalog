"""Filter option resolution — thin delegation to the registry.

In the original main-api this file held a static FILTER_RESOLVERS dict.
In the package, resolvers are registered alongside events in each app's
events.py via catalog.register_filter_resolver(). This module exists only
as a named entry point for the serializer and as a compatibility shim for
any code that imports resolve_filters() directly.
"""
from __future__ import annotations

from .registry import catalog


def resolve_filters(available_filters: list[dict]) -> list[dict]:
    """Return available_filters with any 'source' keys resolved to live options.

    Each filter entry that has a 'source' key has its 'options' replaced by
    the output of the registered resolver for that source key. The 'source'
    key itself is removed from the returned entry.

    Entries without a 'source' key are returned unchanged.

    Args:
        available_filters: List of filter dicts as stored on an EventDefinition.

    Returns:
        New list with source keys resolved to live option lists.
    """
    return catalog._resolve_filters(available_filters)
