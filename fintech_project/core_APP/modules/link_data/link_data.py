import logging
import os
from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from core_APP.modules.link_data.link_data_forms import UploadedFileForm
from core_APP.models import LinkedData
from django.db import transaction


def link_data_view(request):
    """Link Data view."""
    form = UploadedFileForm()
    context = {}
    context.update({'form': form})
    return render(request, 'link_data/link_data.html', context=context)


EXT_TO_SOURCE = {
    ".pdf": "pdf_file",
    ".xlsx": "xlsx_file",
    ".csv": "csv_file",
    ".xls": "xls_file",
    ".txt": "txt_file",
    ".docx": "docx_file",
    ".xlsm": "xlsm_file",
}


@login_required
def handle_upload(request):
    if request.method == "POST":
        form = UploadedFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES["file"]
            _, ext = os.path.splitext(uploaded.name)
            ext = ext.lower()

            data_source = EXT_TO_SOURCE.get(ext)
            if not data_source:
                return redirect("link_data_page")

            with transaction.atomic():
                uf = form.save(commit=False)
                uf.user = request.user
                uf.save()

                LinkedData.objects.create(
                    user=request.user,
                    data_source=data_source,
                    data_id=str(uf.id),
                )
            return redirect("link_data_page")
    return redirect("link_data_page")