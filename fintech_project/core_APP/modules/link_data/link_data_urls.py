from django.urls import path
from .link_data import (
    link_data_view,
    handle_upload
)

urlpatterns = [
    path('', link_data_view, name='link_data_page'),
    path('upload/', handle_upload, name='link_data_upload'),
]
