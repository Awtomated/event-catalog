from django.apps import AppConfig


class EventCatalogConfig(AppConfig):
    name = "event_catalog"
    verbose_name = "Event Catalog"

    def ready(self):
        self._autodiscover_events()

    def _autodiscover_events(self):
        # Walk every installed app and import its events.py if it exists.
        # Same pattern as Django admin's autodiscover_modules('admin').
        from importlib import import_module
        from django.apps import apps

        for app_config in apps.get_app_configs():
            if app_config.name == self.name:
                continue
            try:
                import_module(f"{app_config.name}.events")
            except ImportError:
                pass
