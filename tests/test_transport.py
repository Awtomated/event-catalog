"""Tests for the transport layer and publisher."""
from unittest.mock import MagicMock, patch, call
from django.test import SimpleTestCase, TestCase, override_settings

from event_catalog.transport import get_transport, reset_transport
from event_catalog.transport.base import BaseTransport
from event_catalog.transport.redis_stream import RedisStreamTransport


class GetTransportTest(SimpleTestCase):

    def setUp(self):
        reset_transport()

    def tearDown(self):
        reset_transport()

    @override_settings(EVENT_CATALOG={
        'TRANSPORT': 'event_catalog.transport.redis_stream.RedisStreamTransport',
        'REDIS_URL': 'redis://localhost:6379/0',
    })
    def test_loads_redis_stream_transport(self):
        transport = get_transport()
        self.assertIsInstance(transport, RedisStreamTransport)

    @override_settings(EVENT_CATALOG={
        'TRANSPORT': 'event_catalog.transport.redis_stream.RedisStreamTransport',
    })
    def test_returns_same_instance_on_repeated_calls(self):
        t1 = get_transport()
        t2 = get_transport()
        self.assertIs(t1, t2)

    @override_settings(EVENT_CATALOG={
        'TRANSPORT': 'event_catalog.transport.base.BaseTransport',
    })
    def test_non_transport_class_raises_type_error(self):
        with self.assertRaises(TypeError):
            get_transport()


class RedisStreamTransportTest(SimpleTestCase):

    def setUp(self):
        reset_transport()

    def tearDown(self):
        reset_transport()

    @override_settings(EVENT_CATALOG={
        'REDIS_URL': 'redis://localhost:6379/0',
        'STREAM_NAME': 'event_catalog:events',
    })
    @patch('redis.from_url')
    def test_send_calls_xadd_with_correct_fields(self, mock_from_url):
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        transport = RedisStreamTransport()
        transport.send(
            event_name='file.uploaded',
            org_id='org-1',
            entity_id='file-99',
            entity_scope='file',
            context={'mime_type': 'application/pdf'},
        )

        mock_client.xadd.assert_called_once()
        _, kwargs = mock_client.xadd.call_args
        stream_name = mock_client.xadd.call_args[0][0]
        payload = mock_client.xadd.call_args[0][1]

        self.assertEqual(stream_name, 'event_catalog:events')
        self.assertEqual(payload['event_name'], 'file.uploaded')
        self.assertEqual(payload['org_id'], 'org-1')
        self.assertEqual(payload['entity_id'], 'file-99')
        self.assertEqual(payload['entity_scope'], 'file')
        self.assertIn('context', payload)  # JSON-encoded

    @override_settings(EVENT_CATALOG={
        'REDIS_URL': 'redis://localhost:6379/0',
        'STREAM_NAME': 'custom:stream',
    })
    @patch('redis.from_url')
    def test_custom_stream_name_from_settings(self, mock_from_url):
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        transport = RedisStreamTransport()
        transport.send('x.y', 'o', 'e', 's', {})

        stream_name = mock_client.xadd.call_args[0][0]
        self.assertEqual(stream_name, 'custom:stream')

    @override_settings(EVENT_CATALOG={
        'REDIS_URL': 'redis://localhost:6379/0',
    })
    @patch('redis.from_url')
    def test_default_stream_name_when_not_configured(self, mock_from_url):
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        transport = RedisStreamTransport()
        transport.send('x.y', 'o', 'e', 's', {})

        stream_name = mock_client.xadd.call_args[0][0]
        self.assertEqual(stream_name, 'event_catalog:events')

    @override_settings(EVENT_CATALOG={'REDIS_URL': 'redis://localhost:6379/0'})
    @patch('redis.from_url')
    def test_client_created_lazily_and_cached(self, mock_from_url):
        mock_client = MagicMock()
        mock_from_url.return_value = mock_client

        transport = RedisStreamTransport()
        transport.send('x.y', 'o', 'e', 's', {})
        transport.send('x.y', 'o', 'e', 's', {})

        # redis.from_url called once despite two sends
        mock_from_url.assert_called_once()


class PublisherTest(TestCase):

    def setUp(self):
        reset_transport()

    def tearDown(self):
        reset_transport()

    @patch('event_catalog.publisher.get_transport')
    @patch('event_catalog.publisher.catalog')
    def test_publish_skips_unregistered_event(self, mock_catalog, mock_get_transport):
        mock_catalog.has_active_event.return_value = False

        from event_catalog.publisher import publish
        publish('unknown.event', 'org-1', 'entity-1', 'project', {})

        mock_get_transport.assert_not_called()

    @patch('event_catalog.publisher.get_transport')
    @patch('event_catalog.publisher.catalog')
    def test_publish_defers_send_to_on_commit(self, mock_catalog, mock_get_transport):
        mock_catalog.has_active_event.return_value = True
        mock_transport = MagicMock(spec=BaseTransport)
        mock_get_transport.return_value = mock_transport

        from event_catalog.publisher import publish

        with self.captureOnCommitCallbacks(execute=True):
            publish('project.created', 'org-1', 'entity-1', 'project', {'key': 'val'})

        mock_transport.send.assert_called_once_with(
            'project.created', 'org-1', 'entity-1', 'project', {'key': 'val'},
        )

    @patch('event_catalog.publisher.get_transport')
    @patch('event_catalog.publisher.catalog')
    def test_publish_swallows_transport_exception(self, mock_catalog, mock_get_transport):
        mock_catalog.has_active_event.return_value = True
        mock_transport = MagicMock(spec=BaseTransport)
        mock_transport.send.side_effect = RuntimeError('Redis down')
        mock_get_transport.return_value = mock_transport

        from event_catalog.publisher import publish

        # Should not raise even if transport fails
        with self.captureOnCommitCallbacks(execute=True):
            publish('project.created', 'org-1', 'entity-1', 'project', {})
