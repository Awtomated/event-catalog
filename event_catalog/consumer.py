"""Redis Stream consumer — reads cross-service events and enqueues processing tasks.

Run via Celery beat in main-api. Reads from the shared stream that drive-ms
(and any other external service) writes to via RedisStreamTransport.

Celery beat config (add to main-api's beat schedule):

    CELERY_BEAT_SCHEDULE = {
        'poll-event-stream': {
            'task': 'event_catalog.consumer.poll_event_stream',
            'schedule': 5.0,  # seconds
        },
    }

Settings
--------
    EVENT_CATALOG = {
        ...
        'REDIS_URL':      'redis://localhost:6379/0',
        'STREAM_NAME':    'event_catalog:events',
        'CONSUMER_GROUP': 'main-api',
        'CONSUMER_NAME':  'main-api-worker',
    }
"""
from __future__ import annotations

import json
import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

_DEFAULT_STREAM = 'event_catalog:events'
_DEFAULT_GROUP = 'main-api'
_DEFAULT_CONSUMER = 'main-api-worker'


@shared_task
def poll_event_stream() -> dict:
    """Read a batch of events from the Redis Stream and enqueue processing tasks.

    Uses XREADGROUP for consumer-group semantics — each message is delivered
    to exactly one worker instance. Messages are acknowledged only after the
    Celery task is successfully enqueued, so a crashed worker does not lose
    events (they become pending and can be reclaimed via XAUTOCLAIM).

    Returns:
        Dict with count of messages enqueued this poll cycle.
    """
    import redis

    from .tasks import process_event_triggers

    cfg = getattr(settings, 'EVENT_CATALOG', {})
    redis_url = cfg.get('REDIS_URL', 'redis://localhost:6379/0')
    stream_name = cfg.get('STREAM_NAME', _DEFAULT_STREAM)
    group_name = cfg.get('CONSUMER_GROUP', _DEFAULT_GROUP)
    consumer_name = cfg.get('CONSUMER_NAME', _DEFAULT_CONSUMER)

    r = redis.from_url(redis_url, decode_responses=True)

    # Create the consumer group the first time this runs.
    # '$' means: only process messages arriving *after* group creation.
    # mkstream=True creates the stream itself if it doesn't exist yet.
    try:
        r.xgroup_create(stream_name, group_name, id='$', mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if 'BUSYGROUP' not in str(exc):
            raise  # unexpected error — propagate

    messages = r.xreadgroup(
        group_name,
        consumer_name,
        {stream_name: '>'},  # '>' = only new, undelivered messages
        count=50,
        block=1000,          # wait up to 1 s for messages before returning
    )

    enqueued = 0
    for _, entries in (messages or []):
        for msg_id, fields in entries:
            try:
                process_event_triggers.delay(
                    fields['event_name'],
                    fields['org_id'],
                    fields['entity_id'],
                    fields['entity_scope'],
                    json.loads(fields['context']),
                )
                # Acknowledge only after the task is safely in the Celery queue.
                r.xack(stream_name, group_name, msg_id)
                enqueued += 1

            except Exception:
                logger.exception(
                    "consumer.poll_event_stream: failed to enqueue msg_id=%s "
                    "from stream '%s' — message stays pending for retry",
                    msg_id, stream_name,
                )

    if enqueued:
        logger.info("consumer.poll_event_stream: enqueued %d event(s)", enqueued)

    return {'enqueued': enqueued}
