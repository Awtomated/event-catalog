import django_extensions.db.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    # No dependencies on any other app — this model has zero cross-app FKs.
    # That is the whole point of the refactor.
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='WorkflowTrigger',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('created', django_extensions.db.fields.CreationDateTimeField(
                    auto_now_add=True, verbose_name='created',
                )),
                ('modified', django_extensions.db.fields.ModificationDateTimeField(
                    auto_now=True, verbose_name='modified',
                )),
                ('organisation_id', models.CharField(db_index=True, max_length=255)),
                ('trigger_type', models.CharField(
                    choices=[('event', 'Event'), ('schedule', 'Schedule')],
                    default='event',
                    max_length=20,
                )),
                ('event_name', models.CharField(blank=True, max_length=100)),
                ('event_filters', models.JSONField(blank=True, default=dict)),
                ('entity_source', models.CharField(
                    choices=[('context', 'Context'), ('fixed', 'Fixed')],
                    default='context',
                    max_length=20,
                )),
                ('fixed_entity_scope_slug', models.CharField(blank=True, max_length=50)),
                ('fixed_entity_id', models.CharField(blank=True, max_length=255)),
                ('action_type', models.CharField(max_length=50)),
                ('action_config', models.JSONField(blank=True, default=dict)),
                ('cron_expression', models.CharField(blank=True, max_length=100)),
                ('schedule_timezone', models.CharField(default='UTC', max_length=100)),
                ('temporal_schedule_id', models.CharField(blank=True, max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('fire_count', models.PositiveIntegerField(default=0)),
                ('last_fired_at', models.DateTimeField(blank=True, null=True)),
                ('created_by_id', models.CharField(blank=True, max_length=255)),
            ],
            options={
                'ordering': ['-created'],
            },
        ),
        migrations.AddIndex(
            model_name='workflowtrigger',
            index=models.Index(
                fields=['organisation_id', 'event_name', 'is_active'],
                name='ec_trigger_org_event_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='workflowtrigger',
            index=models.Index(
                fields=['organisation_id', 'trigger_type'],
                name='ec_trigger_org_type_idx',
            ),
        ),
    ]
