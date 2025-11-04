import logging
import os
from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from core_APP.modules.link_data.link_data_forms import UploadedFileForm
from core_APP.models import LinkedData, UploadedFile
from django.db import transaction
from django.db.models import OuterRef, Subquery


EXT_TO_SOURCE = {
    ".pdf": "pdf_file",
    ".xlsx": "xlsx_file",
    ".csv": "csv_file",
    ".xls": "xls_file",
    ".txt": "txt_file",
    ".docx": "docx_file",
    ".xlsm": "xlsm_file",
    ".xml": "xml_file",
    ".json": "json_file",
}


@login_required
def link_data_view(request):
    """Link Data view."""
    form = UploadedFileForm()
    context = {}

    ext_to_source_ls = list(EXT_TO_SOURCE.values())

    data_id_ls = []

    # filter LinkedData for this user and valid sources
    linked_data_qs = LinkedData.objects.filter(
        user=request.user,
        data_source__in=ext_to_source_ls
    )
    for ld in linked_data_qs:
        data_id_ls.append(ld.data_id)

    uploaded_files_qs = UploadedFile.objects.filter(
        id__in=data_id_ls,
        user=request.user
    )

    # Build extension→source mapping (already defined)
    EXT_TO_READABLE = {
        ".pdf": "PDF File",
        ".xlsx": "Excel File (.xlsx)",
        ".csv": "CSV File",
        ".xls": "Excel File (.xls)",
        ".txt": "Text File",
        ".docx": "Word Document",
        ".xlsm": "Macro Excel File",
        ".xml": "XML File",
        ".json": "JSON File",
    }

    for f in uploaded_files_qs:
        ext = os.path.splitext(f.file.name)[1].lower()
        f.data_source = EXT_TO_READABLE.get(ext, "Unknown Type")
        f.file

    context.update({
        "form": form,
        "uploaded_files_qs": uploaded_files_qs,
    })

    return render(request, "link_data/link_data.html", context)


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


@login_required
def link_data_connect_erp(request):
    """Connect ERP."""
    return redirect('link_data_page')


@login_required
def link_data_connect_api(request):
    """Connect API."""
    return redirect('link_data_page')