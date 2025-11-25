from django.db import models
from django.conf import settings
from django.utils import timezone
import os

User = settings.AUTH_USER_MODEL

def user_file_upload_path(instance, filename):
    # Save files under MEDIA_ROOT/user_<id>/<folder_id or root>/<filename>
    folder_part = f"folder_{instance.folder.id}" if instance.folder else "root"
    return os.path.join(f"user_{instance.owner.id}", folder_part, filename)

class Folder(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="folders")
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("owner", "parent", "name")
        ordering = ["-created_at", "name"]

    def __str__(self):
        return self.name

    def path(self):
        # e.g. "Invoices/2025/April"
        parts = []
        cur = self
        while cur:
            parts.append(cur.name)
            cur = cur.parent
        return "/".join(reversed(parts))

class DocumentFile(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
    folder = models.ForeignKey(Folder, null=True, blank=True, on_delete=models.SET_NULL, related_name="files")
    file = models.FileField(upload_to=user_file_upload_path)
    name = models.CharField(max_length=512)
    size = models.PositiveIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=128, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file and not self.size:
            try:
                self.size = self.file.size
            except Exception:
                pass
        if not self.name and self.file:
            self.name = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class UserActionHistory(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="actions")
    action = models.CharField(max_length=128)
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
