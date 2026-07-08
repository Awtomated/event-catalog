# Public API — import these in your app's events.py, signals.py, and
# catalog_action.py files.
#
#   from event_catalog import catalog    # registration + lookup singleton
#   from event_catalog import BaseAction # base class for pluggable actions
#   from event_catalog import publish    # emit an event from a signal handler
#
# Do not import at module level outside of events.py / AppConfig.ready() hooks —
# the registry is only fully populated after Django's app registry is ready.

default_app_config = "event_catalog.apps.EventCatalogConfig"

from event_catalog.registry import catalog      # noqa: E402
from event_catalog.base import BaseAction       # noqa: E402
from event_catalog.publisher import publish     # noqa: E402
