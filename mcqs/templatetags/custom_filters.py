from django import template
from django.utils import timezone
from django.utils.dateparse import parse_datetime

register = template.Library()

@register.filter
def localtime(value):
    # Convert string to datetime if needed
    if isinstance(value, str):
        value = parse_datetime(value)
    
    # Convert to local time
    return timezone.localtime(value) if value else value