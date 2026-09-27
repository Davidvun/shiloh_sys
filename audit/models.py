from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from core.models import User


class ChangeRequestStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class ChangeRequestType(models.TextChoices):
    EDIT = 'edit', 'Edit'
    DELETE = 'delete', 'Delete'


class ChangeRequest(models.Model):
    request_type = models.CharField(max_length=10, choices=ChangeRequestType.choices)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    before_data = models.JSONField(default=dict)
    after_data = models.JSONField(default=dict, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=ChangeRequestStatus.choices, default=ChangeRequestStatus.PENDING)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='change_requests_made')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='change_requests_reviewed')
    admin_notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.request_type.upper()} request by {self.requested_by} [{self.status}]"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, blank=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at}] {self.user} - {self.action} on {self.model_name}"
