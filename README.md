# django-event-catalog

A generic, pluggable event catalog and workflow trigger system for Django. Any
Django service can register its own events and actions. The package handles
matching, routing, and cross-service delivery — your code only describes what
events exist and what to do when they fire.

---

## How it works

```
Your signal fires
  → publish('order.paid', org_id, entity_id, context)
    → transport delivers the event
      → matcher checks WorkflowTrigger filter conditions
        → matching action fires (Temporal, webhook, email, etc.)
```

The package has no knowledge of your domain. You teach it about your models
by registering scopes, events, and actions in plain Python files.

---

## Concepts

| Concept | What it is |
|---|---|
| **EntityScope** | A model that can be an event source (e.g. `project`, `file`, `order`) |
| **EventDefinition** | A named triggerable event emitted by a signal (e.g. `project.status_changed`) |
| **SuggestedTrigger** | A pre-built one-click trigger template shown in the UI |
| **WorkflowTrigger** | A user-created trigger row in the DB linking an event to an action |
| **BaseAction** | Abstract class your action must implement — `fire(trigger, entity_id, context)` |
| **Transport** | How the event travels: in-process Celery task or cross-service Redis Stream |

`EntityScope`, `EventDefinition`, and `SuggestedTrigger` are **in-memory only**
— you declare them in `events.py` files, not in migrations. Only `WorkflowTrigger`
lives in the database.

---

## Installation

### Service that owns triggers and runs the matcher (e.g. main-api)

```bash
pip install -e /path/to/Event-Catalog[full]
```

### Service that only emits events with a separate DB (e.g. drive-ms)

```bash
pip install -e /path/to/Event-Catalog[publisher]
```

---

## Quick start — full service

### 1. Add to INSTALLED_APPS and configure settings

```python
# settings.py
INSTALLED_APPS = [
    ...
    'event_catalog',
]

EVENT_CATALOG = {
    'TRANSPORT': 'event_catalog.transport.celery.CeleryTransport',
}
```

### 2. Run migrations

```bash
python manage.py migrate event_catalog
```

### 3. Register your scopes and events

Create `your_app/events.py`. It is auto-discovered at startup — no import needed
anywhere else.

```python
# your_app/events.py
from event_catalog import catalog
from .models import YourModel

catalog.register_scope(
    'order',
    model='shop.Order',
    label='Order',
    icon='order',
    key_fields=[
        {'name': 'status', 'type': 'str', 'filterable': True},
    ],
)

# Register a filter resolver so status options stay in sync with the model
catalog.register_filter_resolver(
    'order.status_choices',
    lambda: [{'value': v, 'label': l} for v, l in YourModel.STATUS_CHOICES],
)

catalog.register_event(
    scope='order',
    name='order.paid',
    label='Order Paid',
    signal_type='post_save',
    context_schema={'order_id': 'str', 'amount': 'float', 'org_id': 'str'},
    suggestions=[
        {
            'slug': 'sugg_order_paid',
            'label': 'When an order is paid',
            'event_filters': {},
        },
    ],
)

catalog.register_event(
    scope='order',
    name='order.status_changed',
    label='Order Status Changed',
    signal_type='post_save',
    available_filters=[
        {
            'key': 'new_status',
            'type': 'choice',
            'label': 'New Status',
            'source': 'order.status_choices',   # resolved at request time
        },
    ],
    suggestions=[
        {
            'slug': 'sugg_order_shipped',
            'label': 'When an order ships',
            'event_filters': {'new_status': 'shipped'},
        },
    ],
)
```

### 4. Register an action

Create `your_app/catalog_action.py`. Also auto-discovered.

```python
# your_app/catalog_action.py
from event_catalog import catalog, BaseAction

class SendEmailAction(BaseAction):
    action_type = 'send_email'   # stored in DB — never rename without a migration

    def fire(self, trigger, entity_id, context):
        recipient = trigger.action_config['recipient_email']
        template = trigger.action_config['template_id']
        # ... send the email ...

    def get_config_schema(self):
        # Returned by GET /api/event-catalog/actions/ for frontend form rendering
        return {
            'type': 'object',
            'required': ['recipient_email', 'template_id'],
            'properties': {
                'recipient_email': {'type': 'string', 'format': 'email'},
                'template_id': {'type': 'string'},
            },
        }

catalog.register_action('send_email', SendEmailAction())
```

### 5. Emit events from signal handlers

```python
# your_app/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from event_catalog import publish
from .models import Order

_old_status = {}

@receiver(post_save, sender=Order)
def on_order_save(sender, instance, created, **kwargs):
    if created:
        publish(
            event_name='order.paid',
            org_id=str(instance.organisation_id),
            entity_id=str(instance.id),
            entity_scope='order',
            context={
                'order_id': str(instance.id),
                'amount': float(instance.total),
                'org_id': str(instance.organisation_id),
            },
        )
```

`publish()` is a no-op if:
- The event name is not registered or is inactive
- The DB transaction rolls back

### 6. Include the URLs

```python
# your_project/urls.py
from django.urls import include, path

urlpatterns = [
    ...
    path('api/event-catalog/', include('event_catalog.urls')),
]
```

---

## Quick start — publisher-only service (separate DB)

For services like drive-ms that have their own database and cannot query
the `WorkflowTrigger` table.

### 1. Configure settings — no INSTALLED_APPS entry, no migrations

```python
# settings.py
EVENT_CATALOG = {
    'TRANSPORT':   'event_catalog.transport.redis_stream.RedisStreamTransport',
    'REDIS_URL':   'redis://shared-redis:6379/0',   # same Redis instance as main-api
    'STREAM_NAME': 'event_catalog:events',           # must match main-api consumer config
}
```

### 2. Register your scopes and events

```python
# storage/events.py
from event_catalog import catalog

catalog.register_scope('file', model='storage.File', label='File')

catalog.register_event(
    scope='file',
    name='file.uploaded',
    label='File Uploaded',
    signal_type='post_save',
    available_filters=[
        {'key': 'mime_type', 'type': 'str', 'label': 'MIME Type'},
    ],
    suggestions=[
        {'slug': 'sugg_file_uploaded', 'label': 'When a file is uploaded',
         'event_filters': {}},
        {'slug': 'sugg_pdf_uploaded', 'label': 'When a PDF is uploaded',
         'event_filters': {'mime_type': 'application/pdf'}},
    ],
)

catalog.register_event(
    scope='file',
    name='file.deleted',
    label='File Deleted',
    signal_type='post_tombstone',
)
```

### 3. Emit events from signals — identical call

```python
# storage/signals.py
from event_catalog import publish

@receiver(post_save, sender=File)
def on_file_save(sender, instance, created, **kwargs):
    if created:
        publish(
            event_name='file.uploaded',
            org_id=str(instance.org_id),
            entity_id=str(instance.id),
            entity_scope='file',
            context={'mime_type': instance.mime_type, 'size': instance.size},
        )
```

### 4. Configure main-api to consume events from the stream

```python
# main-api/settings.py
EVENT_CATALOG = {
    'TRANSPORT':      'event_catalog.transport.celery.CeleryTransport',
    'REDIS_URL':      'redis://shared-redis:6379/0',
    'STREAM_NAME':    'event_catalog:events',
    'CONSUMER_GROUP': 'main-api',
    'CONSUMER_NAME':  'main-api-worker',
}

# Add to Celery beat schedule
CELERY_BEAT_SCHEDULE = {
    'poll-event-stream': {
        'task': 'event_catalog.consumer.poll_event_stream',
        'schedule': 5.0,   # seconds
    },
}
```

Also register drive-ms's events in main-api so the UI can show them:

```python
# main-api/drive_ms_events.py  (auto-discovered via events.py convention)
from event_catalog import catalog

# Mirror drive-ms registrations so EventCatalogView serves file events
catalog.register_scope('file', model='storage.File', label='File')
catalog.register_event(scope='file', name='file.uploaded', ...)
catalog.register_event(scope='file', name='file.deleted', ...)
```

---

## API reference

All endpoints require authentication.

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/event-catalog/` | Full catalog grouped by scope |
| `GET` | `/api/event-catalog/entity-scopes/` | List registered scopes |
| `GET` | `/api/event-catalog/actions/` | List registered action types and their config schemas |
| `GET` | `/api/event-catalog/triggers/` | List triggers for the user's organisation |
| `POST` | `/api/event-catalog/triggers/` | Create a trigger |
| `GET` | `/api/event-catalog/triggers/<pk>/` | Retrieve a trigger |
| `PATCH` | `/api/event-catalog/triggers/<pk>/` | Update a trigger |
| `DELETE` | `/api/event-catalog/triggers/<pk>/` | Delete a trigger |

### GET /api/event-catalog/ query params

| Param | Type | Description |
|---|---|---|
| `entity_scope` | string | Filter to a single scope slug |
| `scope` | string | Alias for `entity_scope` |
| `include_inactive` | bool | Include events where `is_active=False` |

### POST /api/event-catalog/triggers/ body

```json
{
    "trigger_type": "event",
    "event_name": "order.status_changed",
    "event_filters": {"new_status": "shipped"},
    "entity_source": "context",
    "action_type": "send_email",
    "action_config": {
        "recipient_email": "ops@example.com",
        "template_id": "shipped-confirmation"
    },
    "is_active": true
}
```

For schedule triggers:

```json
{
    "trigger_type": "schedule",
    "cron_expression": "0 9 * * 1",
    "schedule_timezone": "Europe/London",
    "action_type": "send_email",
    "action_config": {"recipient_email": "reports@example.com", "template_id": "weekly"},
    "entity_source": "fixed",
    "fixed_entity_scope_slug": "order",
    "fixed_entity_id": "order-uuid-here"
}
```

---

## Configuration reference

All configuration lives under `settings.EVENT_CATALOG`.

| Key | Required by | Default | Description |
|---|---|---|---|
| `TRANSPORT` | Both | `CeleryTransport` | Dotted path to the transport class |
| `REDIS_URL` | RedisStreamTransport | `redis://localhost:6379/0` | Redis connection URL |
| `STREAM_NAME` | Both | `event_catalog:events` | Redis Stream name (must match across services) |
| `CONSUMER_GROUP` | main-api consumer | `main-api` | Redis consumer group name |
| `CONSUMER_NAME` | main-api consumer | `main-api-worker` | Consumer name within the group |

---

## Filter operators

`event_filters` on a `WorkflowTrigger` supports these formats:

```python
# Simple equality
{"new_status": "shipped"}

# Operator dict
{"new_status": {"op": "eq",      "value": "shipped"}}
{"new_status": {"op": "neq",     "value": "cancelled"}}
{"new_status": {"op": "in",      "value": ["shipped", "delivered"]}}
{"new_status": {"op": "not_in",  "value": ["cancelled", "refunded"]}}
{"note":       {"op": "contains","value": "urgent"}}
```

Empty filters `{}` always fire — the trigger fires on every occurrence of the event.

---

## Overriding the org resolver in views

By default the views extract `organisation_id` from the user object via:
`user.organisation_id` → `user.org_id` → `user.organisation.pk`

If your user model uses a different attribute, subclass the view and override
`_get_org_id`:

```python
# your_project/views.py
from event_catalog.views import WorkflowTriggerListCreateView

class MyTriggerListCreateView(WorkflowTriggerListCreateView):
    def _get_org_id(self, request):
        return str(request.user.profile.org_id)

    def _get_editor_access(self, request):
        return request.user.organisation.has_document_editor_access()
```

```python
# urls.py
path('api/event-catalog/triggers/', MyTriggerListCreateView.as_view()),
```

---

## Running tests

```bash
cd /path/to/Event-Catalog
DJANGO_SETTINGS_MODULE=tests.settings python -m pytest
# or
DJANGO_SETTINGS_MODULE=tests.settings python -m django test tests
```

Test files:

| File | Covers |
|---|---|
| `tests/test_matcher.py` | Pure filter matching logic — all operators |
| `tests/test_registry.py` | Registration, validation, catalog output, resolver resolution |
| `tests/test_transport.py` | Transport loading, RedisStreamTransport, publisher behaviour |
| `tests/test_models.py` | WorkflowTrigger DB operations, queries, atomic counter |

---

## Adding a new event to an existing service

1. Open `your_app/events.py`
2. Call `catalog.register_event(...)` — no migration needed
3. Call `catalog.register_filter_resolver(...)` if the event has dynamic filter options
4. Add signal handler that calls `publish(event_name, ...)`
5. Done — the event appears in `GET /api/event-catalog/` immediately on next deploy

## Adding a new action type

1. Create `your_app/catalog_action.py` (or add to existing one)
2. Subclass `BaseAction`, set `action_type`, implement `fire()` and `get_config_schema()`
3. Call `catalog.register_action('your_type', YourAction())`
4. Done — appears in `GET /api/event-catalog/actions/` immediately on next deploy
# event-catalog
