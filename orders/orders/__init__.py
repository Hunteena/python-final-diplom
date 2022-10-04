from .django_celery import app as celery_app

# Register drf-spectacular extensions
import orders.schema

__all__ = ("celery_app",)
