"""API views for the event catalog and trigger management.

All views require authentication. Organisation scoping is handled via the
OrgScopedMixin — override _get_org_id() in your project's subclass if the
default user attribute lookup doesn't fit your user model.

Include URLs in your project:

    path('api/event-catalog/', include('event_catalog.urls')),
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WorkflowTrigger
from .registry import catalog
from .serializers import (
    WorkflowTriggerReadSerializer,
    WorkflowTriggerWriteSerializer,
)


# ── Mixin ──────────────────────────────────────────────────────────────────────

class OrgScopedMixin:
    """Extract organisation_id from the authenticated user.

    Override _get_org_id() in your project if the default attribute lookup
    doesn't match your User model. The method must return a string or None.

    Default lookup order:
        user.organisation_id  →  user.org_id  →  user.organisation.pk
    """

    def _get_org_id(self, request) -> str | None:
        user = request.user
        for attr in ('organisation_id', 'org_id'):
            val = getattr(user, attr, None)
            if val is not None:
                return str(val)
        org = getattr(user, 'organisation', None)
        if org is not None:
            return str(org.pk)
        return None

    def _require_org_id(self, request) -> tuple[str | None, Response | None]:
        """Return (org_id, None) on success or (None, error_response) on failure."""
        org_id = self._get_org_id(request)
        if org_id is None:
            return None, Response(
                {'error': 'No organisation found for this user.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return org_id, None

    def _get_editor_access(self, request) -> bool:
        """Return True if the user's org has document editor access.

        Override in your project to wire up your actual permission check,
        e.g. has_document_editor_access(request.user.organisation).
        """
        return False


# ── Catalog views ──────────────────────────────────────────────────────────────

class EventCatalogView(OrgScopedMixin, APIView):
    """GET /api/event-catalog/

    Return the full event catalog grouped by entity scope. Used by the
    frontend to populate the trigger-builder scope and event pickers.

    Query params:
        entity_scope (str)       — filter to a single scope slug
        scope (str)              — alias for entity_scope (backward compat)
        include_inactive (bool)  — include events where is_active=False
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        scope_slug = (
            request.query_params.get('entity_scope')
            or request.query_params.get('scope')
        )
        include_inactive = (
            request.query_params.get('include_inactive', '').lower() == 'true'
        )
        editor_access = self._get_editor_access(request)

        data = catalog.get_catalog(
            scope_slug=scope_slug,
            editor_access=editor_access,
            include_inactive=include_inactive,
        )
        return Response(data)


class EntityScopeListView(OrgScopedMixin, APIView):
    """GET /api/event-catalog/entity-scopes/

    Return a flat list of all registered entity scopes with their metadata.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        scopes = [catalog._scope_to_dict(s) for s in catalog.get_scopes()]
        return Response(scopes)


class ActionTypeListView(OrgScopedMixin, APIView):
    """GET /api/event-catalog/actions/

    Return all registered action types and their config JSON schemas.
    The frontend uses this to render the correct config form when a user
    selects an action type while building a trigger.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(catalog.get_registered_action_types())


# ── Trigger CRUD views ─────────────────────────────────────────────────────────

class WorkflowTriggerListCreateView(OrgScopedMixin, APIView):
    """GET/POST /api/event-catalog/triggers/

    GET  — list all triggers for the user's organisation.
    POST — create a new trigger scoped to the user's organisation.

    GET query params:
        event_name (str)    — filter by event name
        trigger_type (str)  — filter by 'event' or 'schedule'
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        org_id, err = self._require_org_id(request)
        if err:
            return err

        qs = WorkflowTrigger.objects.filter(organisation_id=org_id)

        event_name = request.query_params.get('event_name')
        if event_name:
            qs = qs.filter(event_name=event_name)

        trigger_type = request.query_params.get('trigger_type')
        if trigger_type:
            qs = qs.filter(trigger_type=trigger_type)

        serializer = WorkflowTriggerReadSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request) -> Response:
        org_id, err = self._require_org_id(request)
        if err:
            return err

        serializer = WorkflowTriggerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trigger = serializer.save(
            organisation_id=org_id,
            created_by_id=str(request.user.pk),
        )
        return Response(
            WorkflowTriggerReadSerializer(trigger).data,
            status=status.HTTP_201_CREATED,
        )


class WorkflowTriggerDetailView(OrgScopedMixin, APIView):
    """GET/PATCH/DELETE /api/event-catalog/triggers/<pk>/

    All operations are scoped to the authenticated user's organisation —
    a trigger belonging to a different org returns 404 (not 403) to avoid
    leaking existence information.
    """
    permission_classes = [IsAuthenticated]

    def _get_trigger(self, request, pk: int) -> WorkflowTrigger | None:
        org_id = self._get_org_id(request)
        try:
            return WorkflowTrigger.objects.get(pk=pk, organisation_id=org_id)
        except WorkflowTrigger.DoesNotExist:
            return None

    def get(self, request, pk: int) -> Response:
        trigger = self._get_trigger(request, pk)
        if trigger is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(WorkflowTriggerReadSerializer(trigger).data)

    def patch(self, request, pk: int) -> Response:
        trigger = self._get_trigger(request, pk)
        if trigger is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = WorkflowTriggerWriteSerializer(
            trigger, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        trigger = serializer.save()
        return Response(WorkflowTriggerReadSerializer(trigger).data)

    def delete(self, request, pk: int) -> Response:
        trigger = self._get_trigger(request, pk)
        if trigger is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        trigger.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
