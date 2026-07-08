"""Tests for the WorkflowTrigger model."""
from django.test import TestCase

from event_catalog.models import WorkflowTrigger


class WorkflowTriggerCreationTest(TestCase):

    def _make_event_trigger(self, **kwargs):
        defaults = dict(
            organisation_id='org-abc',
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='project.status_changed',
            event_filters={'new_status': 'in_progress'},
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 42},
        )
        defaults.update(kwargs)
        return WorkflowTrigger.objects.create(**defaults)

    def test_creates_event_trigger(self):
        t = self._make_event_trigger()
        self.assertIsNotNone(t.pk)
        self.assertEqual(t.organisation_id, 'org-abc')
        self.assertEqual(t.event_name, 'project.status_changed')
        self.assertEqual(t.action_type, 'temporal_workflow')
        self.assertEqual(t.action_config, {'organisation_workflow_id': 42})

    def test_defaults(self):
        t = self._make_event_trigger()
        self.assertTrue(t.is_active)
        self.assertEqual(t.fire_count, 0)
        self.assertIsNone(t.last_fired_at)
        self.assertEqual(t.entity_source, WorkflowTrigger.EntitySource.CONTEXT)
        self.assertEqual(t.schedule_timezone, 'UTC')
        self.assertEqual(t.event_filters, {'new_status': 'in_progress'})

    def test_str_event_trigger(self):
        t = self._make_event_trigger()
        self.assertIn('project.status_changed', str(t))
        self.assertIn('temporal_workflow', str(t))
        self.assertIn('org-abc', str(t))

    def test_str_schedule_trigger(self):
        t = WorkflowTrigger.objects.create(
            organisation_id='org-abc',
            trigger_type=WorkflowTrigger.TriggerType.SCHEDULE,
            cron_expression='0 9 * * 1',
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 7},
        )
        self.assertIn('0 9 * * 1', str(t))
        self.assertIn('temporal_workflow', str(t))

    def test_created_and_modified_auto_populated(self):
        t = self._make_event_trigger()
        self.assertIsNotNone(t.created)
        self.assertIsNotNone(t.modified)

    def test_empty_event_filters_matches_all(self):
        t = self._make_event_trigger(event_filters={})
        self.assertEqual(t.event_filters, {})

    def test_complex_action_config_stored_as_json(self):
        config = {
            'organisation_workflow_id': 42,
            'extra': {'nested': True, 'values': [1, 2, 3]},
        }
        t = self._make_event_trigger(action_config=config)
        t.refresh_from_db()
        self.assertEqual(t.action_config, config)


class WorkflowTriggerQueryTest(TestCase):

    def setUp(self):
        WorkflowTrigger.objects.create(
            organisation_id='org-1',
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='project.status_changed',
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 1},
            is_active=True,
        )
        WorkflowTrigger.objects.create(
            organisation_id='org-1',
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='project.status_changed',
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 2},
            is_active=False,  # inactive
        )
        WorkflowTrigger.objects.create(
            organisation_id='org-2',
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='project.status_changed',
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 3},
            is_active=True,
        )
        WorkflowTrigger.objects.create(
            organisation_id='org-1',
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='task.created',
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 4},
            is_active=True,
        )

    def test_filter_by_org_and_event_name(self):
        qs = WorkflowTrigger.objects.filter(
            organisation_id='org-1',
            event_name='project.status_changed',
        )
        self.assertEqual(qs.count(), 2)

    def test_filter_active_only(self):
        qs = WorkflowTrigger.objects.filter(
            organisation_id='org-1',
            event_name='project.status_changed',
            is_active=True,
        )
        self.assertEqual(qs.count(), 1)

    def test_index_lookup_for_celery_transport(self):
        # Simulates the exact query CeleryTransport.send() runs for early exit.
        exists = WorkflowTrigger.objects.filter(
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='project.status_changed',
            organisation_id='org-1',
            is_active=True,
        ).exists()
        self.assertTrue(exists)

    def test_no_match_returns_false(self):
        exists = WorkflowTrigger.objects.filter(
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='unknown.event',
            organisation_id='org-1',
            is_active=True,
        ).exists()
        self.assertFalse(exists)

    def test_fire_count_atomic_increment(self):
        from django.db.models import F

        trigger = WorkflowTrigger.objects.filter(
            organisation_id='org-1', event_name='task.created',
        ).first()
        WorkflowTrigger.objects.filter(pk=trigger.pk).update(
            fire_count=F('fire_count') + 1
        )
        trigger.refresh_from_db()
        self.assertEqual(trigger.fire_count, 1)


class WorkflowTriggerFixedEntityTest(TestCase):

    def test_fixed_entity_source_stores_scope_slug_and_id(self):
        t = WorkflowTrigger.objects.create(
            organisation_id='org-1',
            trigger_type=WorkflowTrigger.TriggerType.EVENT,
            event_name='project.created',
            entity_source=WorkflowTrigger.EntitySource.FIXED,
            fixed_entity_scope_slug='project',
            fixed_entity_id='proj-uuid-123',
            action_type='temporal_workflow',
            action_config={'organisation_workflow_id': 5},
        )
        t.refresh_from_db()
        self.assertEqual(t.entity_source, WorkflowTrigger.EntitySource.FIXED)
        self.assertEqual(t.fixed_entity_scope_slug, 'project')
        self.assertEqual(t.fixed_entity_id, 'proj-uuid-123')
