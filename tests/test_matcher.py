from django.test import SimpleTestCase

from event_catalog.matcher import filters_match


class FiltersMatchTest(SimpleTestCase):

    def test_empty_filters_always_match(self):
        self.assertTrue(filters_match({}, {'new_status': 'in_progress'}))
        self.assertTrue(filters_match({}, {}))

    def test_simple_equality_match(self):
        self.assertTrue(filters_match({'new_status': 'in_progress'}, {'new_status': 'in_progress'}))

    def test_simple_equality_no_match(self):
        self.assertFalse(filters_match({'new_status': 'in_progress'}, {'new_status': 'done'}))

    def test_missing_context_key_is_no_match(self):
        self.assertFalse(filters_match({'new_status': 'in_progress'}, {}))

    def test_multiple_filters_all_must_match(self):
        filters = {'new_status': 'done', 'was_unassigned': True}
        self.assertTrue(filters_match(filters, {'new_status': 'done', 'was_unassigned': True}))
        self.assertFalse(filters_match(filters, {'new_status': 'done', 'was_unassigned': False}))

    def test_op_eq(self):
        self.assertTrue(filters_match({'status': {'op': 'eq', 'value': 'done'}}, {'status': 'done'}))
        self.assertFalse(filters_match({'status': {'op': 'eq', 'value': 'done'}}, {'status': 'todo'}))

    def test_op_neq(self):
        self.assertTrue(filters_match({'status': {'op': 'neq', 'value': 'todo'}}, {'status': 'done'}))
        self.assertFalse(filters_match({'status': {'op': 'neq', 'value': 'todo'}}, {'status': 'todo'}))

    def test_op_in(self):
        f = {'status': {'op': 'in', 'value': ['done', 'closed']}}
        self.assertTrue(filters_match(f, {'status': 'done'}))
        self.assertTrue(filters_match(f, {'status': 'closed'}))
        self.assertFalse(filters_match(f, {'status': 'todo'}))

    def test_op_not_in(self):
        f = {'status': {'op': 'not_in', 'value': ['todo', 'archive']}}
        self.assertTrue(filters_match(f, {'status': 'done'}))
        self.assertFalse(filters_match(f, {'status': 'todo'}))

    def test_op_contains(self):
        f = {'description': {'op': 'contains', 'value': 'urgent'}}
        self.assertTrue(filters_match(f, {'description': 'this is urgent'}))
        self.assertFalse(filters_match(f, {'description': 'normal task'}))

    def test_op_contains_non_string_actual_is_no_match(self):
        f = {'count': {'op': 'contains', 'value': '5'}}
        self.assertFalse(filters_match(f, {'count': 5}))

    def test_unknown_op_is_no_match(self):
        f = {'status': {'op': 'regex', 'value': '^done$'}}
        self.assertFalse(filters_match(f, {'status': 'done'}))

    def test_boolean_value_match(self):
        self.assertTrue(filters_match({'was_unassigned': True}, {'was_unassigned': True}))
        self.assertFalse(filters_match({'was_unassigned': True}, {'was_unassigned': False}))
