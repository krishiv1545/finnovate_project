from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import uuid

# Create your models here.

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        (1, 'admin'),
        (2, 'user'),
    )
    user_type = models.PositiveSmallIntegerField(choices=USER_TYPE_CHOICES, default=2)

    def __str__(self):
        return self.username
    
    class Meta:
        db_table = 'Users'


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'conversations'
        ordering = ['-updated_at']


class Message(models.Model):
    ROLE_CHOICES = (
        ('user', 'user'),
        ('assistant', 'assistant'),
        ('system', 'system'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']


class LinkedData(models.Model):
    data_source_options = (
        ('pdf_file', 'PDF File'),
        ('xlsx_file', 'XLSX File'),
        ('csv_file', 'CSV File'),
        ('google_sheet', 'Google Sheet'),
        ('xls_file', 'XLS File'),
        ('txt_file', 'Text File'),
        ('docx_file', 'DOCX File'),
        ('xlsm_file', 'XLSM File'),
        ('xml_file', 'XML File'),
        ('json_file', 'JSON File'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='linked_data')
    data_source = models.CharField(max_length=50, choices=data_source_options)
    data_id = models.CharField(max_length=255, null=True, blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'linked_data'
        ordering = ['-linked_at']


class UploadedFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_files')
    file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'uploaded_files'
        ordering = ['-uploaded_at']