from django.core.management.base import BaseCommand
from django.core.serializers import serialize
from django.apps import apps
import json

class Command(BaseCommand):
    help = 'Export data from all models to a JSON file'

    def add_arguments(self, parser):
        parser.add_argument('output_file', type=str, help='Path to the output JSON file')

    def handle(self, *args, **kwargs):
        output_file = kwargs['output_file']

        data_dict = {}
        for model in apps.get_models():
            model_name = model._meta.model_name
            app_label = model._meta.app_label
            model_data = serialize('json', model.objects.all())
            data_dict[f'{app_label}.{model_name}'] = model_data

        with open(output_file, 'w') as file:
            json.dump(data_dict, file, indent=2)

        self.stdout.write(self.style.SUCCESS(f'Successfully exported all data to {output_file}'))
