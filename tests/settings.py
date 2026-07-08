"""Minimal Django settings for running the event_catalog test suite.

Usage:
    DJANGO_SETTINGS_MODULE=tests.settings python -m pytest
    # or
    DJANGO_SETTINGS_MODULE=tests.settings python manage.py test tests
"""

SECRET_KEY = 'test-only-not-for-production'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'event_catalog',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery — synchronous execution in tests (no broker needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EVENT_CATALOG = {
    'TRANSPORT': 'event_catalog.transport.celery.CeleryTransport',
}
