# app/templatetags/custom_filters.py
import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def json_to_list(value):
    """Converts a JSON string (like stored options) into a Python list."""
    if not value:
        return []

    # Safely load the JSON string into a Python list/dict
    try:
        data = json.loads(value)
        # Ensure that if it loads, it's an iterable list (or convert a comma-separated string)
        if isinstance(data, list):
            return data
        # Handle cases where it might be a simple string representation of options
        elif isinstance(data, str) and "," in data:
            return [item.strip() for item in data.split(",")]
        return []
    except (json.JSONDecodeError, TypeError):
        # Fallback if it's just a comma-separated string without proper JSON formatting
        if isinstance(value, str):
            return [item.strip() for item in value.split(",")]
        return []
