from django.db import models
from django.contrib.auth.models import User
from mcqs.models import MCQ, TestSession
import uuid
from django.utils import timezone

class ConnectionRequest(models.Model):
    from_user = models.ForeignKey(User, related_name='sent_requests', on_delete=models.CASCADE)
    to_user = models.ForeignKey(User, related_name='received_requests', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request from {self.from_user.username} to {self.to_user.username}"

# Create your models here.
class Connection(models.Model):
    user = models.ForeignKey(User, related_name='connections', on_delete=models.CASCADE)
    connected_user = models.ForeignKey(User, related_name='connected_to', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} is connected to {self.connected_user.username}"

from datetime import datetime
class Shared_Bookmark(models.Model):
    sb_uid = models.CharField(max_length=100, unique=True, null=True, blank=True)    
    mcq = models.ForeignKey(MCQ, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='sent_mcqs', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_mcqs', on_delete=models.CASCADE)
    shared_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"MCQ {self.mcq.text} shared by {self.sender.username} to {self.recipient.username} on {self.shared_at}"




from datetime import datetime

class Shared_Test(models.Model):
    st_uid = models.CharField(max_length=100, unique=True, null=True, blank=True)  # Unique identifier for the shared test
    test_session = models.ForeignKey(TestSession, on_delete=models.CASCADE)  # Foreign key to the TestSession model
    sender = models.ForeignKey(User, related_name='sent_tests', on_delete=models.CASCADE)  # User who shared the test
    recipient = models.ForeignKey(User, related_name='received_tests', on_delete=models.CASCADE)  # User who received the test
    shared_at = models.DateTimeField(default=timezone.now)# Timestamp for when the test was shared
    started = models.BooleanField(default=False)
    new_test = models.CharField(max_length=100, unique=True, null=True, blank=True)
    def __str__(self):
        return f"TestSession {self.test_session.test_id} shared by {self.sender.username} to {self.recipient.username} on {self.shared_at}"

