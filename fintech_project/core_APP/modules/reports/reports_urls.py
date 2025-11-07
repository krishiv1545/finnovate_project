from django.urls import path

from .reports import reports_view, balance_sheet_view


urlpatterns = [
    path('', reports_view, name='reports_page'),
    path('tier3/', balance_sheet_view, name='reports_tier3'),
]

