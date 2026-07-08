"""Tests for EventRegistry — registration, validation, and catalog output."""
from django.test import SimpleTestCase

from event_catalog.registry import EventRegistry
from event_catalog.base import BaseAction


def _make_registry():
    """Return a fresh registry (not the global singleton) for each test."""
    return EventRegistry()


class RegisterScopeTest(SimpleTestCase):

    def test_registers_scope(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        scope = r.get_scope('project')
        self.assertEqual(scope.slug, 'project')
        self.assertEqual(scope.model, 'project.Project')
        self.assertEqual(scope.label, 'Project')

    def test_verbose_name_plural_defaults_to_label_plus_s(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        self.assertEqual(r.get_scope('project').verbose_name_plural, 'Projects')

    def test_duplicate_slug_raises(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        with self.assertRaises(ValueError):
            r.register_scope('project', model='project.Project', label='Project')

    def test_unknown_slug_returns_none(self):
        r = _make_registry()
        self.assertIsNone(r.get_scope('nonexistent'))


class RegisterEventTest(SimpleTestCase):

    def _registry_with_scope(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        return r

    def test_registers_event(self):
        r = self._registry_with_scope()
        r.register_event(
            scope='project',
            name='project.created',
            label='Project Created',
            signal_type='post_save',
        )
        event = r.get_event('project.created')
        self.assertEqual(event.name, 'project.created')
        self.assertEqual(event.scope, 'project')

    def test_unknown_scope_raises(self):
        r = _make_registry()
        with self.assertRaises(ValueError):
            r.register_event(
                scope='nonexistent',
                name='x.y',
                label='X',
                signal_type='post_save',
            )

    def test_duplicate_event_name_raises(self):
        r = self._registry_with_scope()
        r.register_event(scope='project', name='project.created',
                         label='Project Created', signal_type='post_save')
        with self.assertRaises(ValueError):
            r.register_event(scope='project', name='project.created',
                             label='Duplicate', signal_type='post_save')

    def test_suggestions_are_built(self):
        r = self._registry_with_scope()
        r.register_event(
            scope='project',
            name='project.status_changed',
            label='Project Status Changed',
            signal_type='post_save',
            suggestions=[
                {'slug': 'sugg_started', 'label': 'When a project starts',
                 'event_filters': {'new_status': 'in_progress'}},
            ],
        )
        event = r.get_event('project.status_changed')
        self.assertEqual(len(event.suggestions), 1)
        self.assertEqual(event.suggestions[0].slug, 'sugg_started')
        self.assertEqual(event.suggestions[0].event_name, 'project.status_changed')

    def test_inactive_events_excluded_by_default(self):
        r = self._registry_with_scope()
        r.register_event(scope='project', name='project.created',
                         label='Created', signal_type='post_save', is_active=False)
        self.assertEqual(r.get_events(), [])

    def test_inactive_events_included_when_requested(self):
        r = self._registry_with_scope()
        r.register_event(scope='project', name='project.created',
                         label='Created', signal_type='post_save', is_active=False)
        self.assertEqual(len(r.get_events(include_inactive=True)), 1)

    def test_editor_access_events_excluded_by_default(self):
        r = self._registry_with_scope()
        r.register_event(scope='project', name='document.segment_locked',
                         label='Segment Locked', signal_type='post_save',
                         requires_editor_access=True)
        self.assertEqual(r.get_events(), [])

    def test_editor_access_events_included_when_access_granted(self):
        r = self._registry_with_scope()
        r.register_event(scope='project', name='document.segment_locked',
                         label='Segment Locked', signal_type='post_save',
                         requires_editor_access=True)
        self.assertEqual(len(r.get_events(editor_access=True)), 1)


class RegisterActionTest(SimpleTestCase):

    def test_registers_action(self):
        class DummyAction(BaseAction):
            action_type = 'dummy'
            def fire(self, trigger, entity_id, context): pass

        r = _make_registry()
        r.register_action('dummy', DummyAction())
        action = r.get_action('dummy')
        self.assertIsInstance(action, DummyAction)

    def test_non_base_action_raises(self):
        r = _make_registry()
        with self.assertRaises(TypeError):
            r.register_action('bad', object())

    def test_duplicate_action_type_raises(self):
        class DummyAction(BaseAction):
            action_type = 'dummy'
            def fire(self, trigger, entity_id, context): pass

        r = _make_registry()
        r.register_action('dummy', DummyAction())
        with self.assertRaises(ValueError):
            r.register_action('dummy', DummyAction())

    def test_unknown_action_type_raises_key_error(self):
        r = _make_registry()
        with self.assertRaises(KeyError):
            r.get_action('nonexistent')


class FilterResolverTest(SimpleTestCase):

    def test_registers_and_resolves(self):
        r = _make_registry()
        r.register_filter_resolver(
            'project.status_choices',
            lambda: [{'value': 'done', 'label': 'Done'}],
        )
        options = r.resolve_filter_options('project.status_choices')
        self.assertEqual(options, [{'value': 'done', 'label': 'Done'}])

    def test_missing_resolver_returns_empty_list(self):
        r = _make_registry()
        self.assertEqual(r.resolve_filter_options('nonexistent'), [])

    def test_duplicate_resolver_raises(self):
        r = _make_registry()
        r.register_filter_resolver('key', lambda: [])
        with self.assertRaises(ValueError):
            r.register_filter_resolver('key', lambda: [])

    def test_filters_resolved_in_get_catalog(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        r.register_filter_resolver(
            'project.status_choices',
            lambda: [{'value': 'done', 'label': 'Done'}],
        )
        r.register_event(
            scope='project',
            name='project.status_changed',
            label='Status Changed',
            signal_type='post_save',
            available_filters=[
                {'key': 'new_status', 'type': 'choice', 'label': 'New Status',
                 'source': 'project.status_choices'},
            ],
        )
        catalog = r.get_catalog()
        filters = catalog['project']['events'][0]['available_filters']
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['options'], [{'value': 'done', 'label': 'Done'}])
        self.assertNotIn('source', filters[0])  # source key is stripped from response


class GetCatalogTest(SimpleTestCase):

    def _full_registry(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project', order=0)
        r.register_scope('task', model='project.Task', label='Task', order=1)
        r.register_event(scope='project', name='project.created',
                         label='Project Created', signal_type='post_save',
                         suggestions=[{'slug': 'sugg_p', 'label': 'When project created'}])
        r.register_event(scope='task', name='task.created',
                         label='Task Created', signal_type='post_save')
        return r

    def test_catalog_has_all_scopes(self):
        r = self._full_registry()
        catalog = r.get_catalog()
        self.assertIn('project', catalog)
        self.assertIn('task', catalog)

    def test_catalog_scope_filtered(self):
        r = self._full_registry()
        catalog = r.get_catalog(scope_slug='project')
        self.assertIn('project', catalog)
        self.assertNotIn('task', catalog)

    def test_suggestions_rolled_up_per_scope(self):
        r = self._full_registry()
        catalog = r.get_catalog()
        self.assertEqual(len(catalog['project']['suggested_triggers']), 1)
        self.assertEqual(catalog['project']['suggested_triggers'][0]['id'], 'sugg_p')

    def test_has_active_event_true(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        r.register_event(scope='project', name='project.created',
                         label='Created', signal_type='post_save')
        self.assertTrue(r.has_active_event('project.created'))

    def test_has_active_event_false_when_inactive(self):
        r = _make_registry()
        r.register_scope('project', model='project.Project', label='Project')
        r.register_event(scope='project', name='project.created',
                         label='Created', signal_type='post_save', is_active=False)
        self.assertFalse(r.has_active_event('project.created'))

    def test_has_active_event_false_when_missing(self):
        r = _make_registry()
        self.assertFalse(r.has_active_event('does.not.exist'))
