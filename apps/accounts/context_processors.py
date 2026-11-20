from django.conf import settings


def dev_mode(request):
    """Exposes ENABLE_DEV_SWITCHER to templates."""
    return {
        'enable_dev_switcher': getattr(settings, 'ENABLE_DEV_SWITCHER', False),
    }
