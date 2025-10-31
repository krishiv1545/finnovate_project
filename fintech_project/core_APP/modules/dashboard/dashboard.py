import logging
from django.shortcuts import render
from django.shortcuts import redirect
from django.contrib import messages


def dashboard_view(request):
    """Dashboard view."""
    return render(request, 'dashboard/dashboard.html')