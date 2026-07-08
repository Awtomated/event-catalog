"""URL patterns for the event_catalog package.

Include in your project's root urls.py:

    path('api/event-catalog/', include('event_catalog.urls')),

This gives you:

    GET  /api/event-catalog/                     EventCatalogView
    GET  /api/event-catalog/entity-scopes/       EntityScopeListView
    GET  /api/event-catalog/actions/             ActionTypeListView
    GET  /api/event-catalog/triggers/            WorkflowTriggerListCreateView
    POST /api/event-catalog/triggers/            WorkflowTriggerListCreateView
    GET  /api/event-catalog/triggers/<pk>/       WorkflowTriggerDetailView
    PATCH /api/event-catalog/triggers/<pk>/      WorkflowTriggerDetailView
    DELETE /api/event-catalog/triggers/<pk>/     WorkflowTriggerDetailView
"""
from django.urls import path

from .views import (
    ActionTypeListView,
    EntityScopeListView,
    EventCatalogView,
    WorkflowTriggerDetailView,
    WorkflowTriggerListCreateView,
)

urlpatterns = [
    path('', EventCatalogView.as_view(), name='event-catalog'),
    path('entity-scopes/', EntityScopeListView.as_view(), name='event-catalog-entity-scopes'),
    path('actions/', ActionTypeListView.as_view(), name='event-catalog-actions'),
    path('triggers/', WorkflowTriggerListCreateView.as_view(), name='event-catalog-triggers'),
    path('triggers/<int:pk>/', WorkflowTriggerDetailView.as_view(), name='event-catalog-trigger-detail'),
]
