from django.urls import path
from .dashboard import (
    dashboard_view,
)

urlpatterns = [
    path('', dashboard_view, name='dashboard_view'),
]
