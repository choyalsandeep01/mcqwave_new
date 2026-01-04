from django.db import models
from base.models import BaseModel
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid
from base.email import send_account_activation_email
from mcqs.models import MCQ
from django.contrib.auth import get_user_model

# Create your models here.
class Profile(BaseModel):
    user = models.OneToOneField(User , on_delete=models.CASCADE , related_name="profile", null=True)
    is_email_verified = models.BooleanField(default=False)
    email_token = models.CharField(max_length=100 , null=True , blank=True)
    profile_image = models.ImageField(upload_to='profile/', null=True, blank=True)
    reset_token = models.CharField(max_length=100, null=True, blank=True)  # New field for password reset token
    current_test = models.CharField(max_length=100, null=True, blank=True)  # New field for password reset token
    hive_current_test = models.CharField(max_length=100, null=True, blank=True)  # New field for password reset token
    mock_current_test = models.CharField(max_length=100, null=True, blank=True)  # New field for password reset token
    pyq_test = models.CharField(max_length=100, null=True, blank=True)  # New field for password reset token
    flashcard_free_sessions = models.IntegerField(default=0, help_text="Number of free flashcard sessions attempted by the user") 

    medical_college = models.ForeignKey(
        'MedicalCollege',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students'
    )
    other_medical_college = models.CharField(max_length=100, null=True, blank=True)
    mobile_number = models.CharField(max_length=15, blank=True, null=True)
    is_mobile_verified = models.BooleanField(default=False)
    free_mcq_attempted = models.IntegerField(default=0, help_text="Number of free MCQs attempted by the user")


    def __str__(self):
        return self.user.username
    
    @property
    def free_mcqs_remaining(self):
        """Calculate remaining free MCQs (out of 100)"""
        FREE_MCQ_LIMIT = 100
        return max(0, FREE_MCQ_LIMIT - self.free_mcq_attempted)
    
    @property
    def has_free_mcqs_left(self):
        """Check if user has free MCQs remaining"""
        return self.free_mcqs_remaining > 0
    
    def can_attempt_test(self, test_mcq_count):
        """Check if user can attempt a test with given MCQ count"""
        return self.free_mcqs_remaining >= test_mcq_count
    
    def consume_free_mcqs(self, count):
        """Consume free MCQs when user attempts a test"""
        if self.has_free_mcqs_left:
            self.free_mcq_attempted += count
            self.save()
            return True
        return False
    @property
    def flashcard_sessions_remaining(self):
        """Calculate remaining free flashcard sessions (out of 3)"""
        FREE_SESSION_LIMIT = 3
        return max(0, FREE_SESSION_LIMIT - self.flashcard_free_sessions)
    
    @property
    def has_flashcard_sessions_left(self):
        """Check if user has free flashcard sessions remaining"""
        return self.flashcard_sessions_remaining > 0
    
    def consume_flashcard_session(self):
        """Consume one free flashcard session"""
        if self.has_flashcard_sessions_left or self.flashcard_sessions_remaining >= 0:
            self.flashcard_free_sessions += 1
            self.save()
            return True
        return False
@receiver(post_save , sender = User)
def  send_email_token(sender , instance , created , **kwargs):
    try:
        if created:
            email_token = str(uuid.uuid4())
            Profile.objects.create(user = instance , email_token = email_token)
            email = instance.email
            send_account_activation_email(email , email_token)

    except Exception as e:
        print(e)

class OTPVerification(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.otp_code:
            self.otp_code = ''.join(random.choices(string.digits, k=6))
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.username} - {self.mobile_number} - {self.otp_code}"
        
class Feedback(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('implemented', 'Implemented'),
        ('declined', 'Declined'),
        ('archived', 'Archived'),
    ]
    
    CATEGORY_CHOICES = [
        ('platform', 'Platform Experience'),
        ('content', 'Question Content'),
        ('feature', 'Feature Suggestion'),
        ('performance', 'Performance'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, null=True, help_text="Internal notes about this feedback")
    admin_response = models.TextField(blank=True, null=True, help_text="Response sent to the user")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='reviewed_feedback'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'

    def __str__(self):
        return f"Feedback from {self.user.username} - {self.get_status_display()}"

    def mark_as_reviewed(self, admin_user):
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()

class Contact(models.Model):
    SUBJECT_CHOICES = [
        ('technical', 'Technical Support'),
        ('billing', 'Billing Inquiry'),
        ('account', 'Account Help'),
        ('other', 'Other Assistance'),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=20, choices=SUBJECT_CHOICES)
    message = models.TextField()
    user = models.ForeignKey(
        get_user_model(), 
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} - {self.subject} ({self.created_at.strftime('%Y-%m-%d')})"

    class Meta:
        ordering = ['-created_at']


class VisitorCount(models.Model):
    path = models.CharField(max_length=255, unique=True)
    count = models.PositiveIntegerField(default=0)
    last_visit = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.path} - {self.count} visits"
    
    @classmethod
    def increment(cls, path):
        obj, created = cls.objects.get_or_create(path=path)
        obj.count += 1
        obj.save()
        return obj.count
        
    @classmethod
    def get_total_visits(cls):
        return cls.objects.filter(path='/').first().count if cls.objects.filter(path='/').exists() else 0

NOTIFICATION_TYPES = [
    ('new_mock', 'New Mock Test Available'),
    ('mock_rank', 'Mock Test Rank Updated'),
    ('incomplete_mock', 'Incomplete Mock Test'),
    ('incomplete_practice', 'Incomplete Practice Session'),
    ('practice_reminder', 'Practice Reminder'),
    ('mock_reminder', 'Mock Test Reminder'),
    ('streak', 'Practice Streak'),
    ('feedback_response', 'Feedback Response'),
]

class Notification(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    related_mock = models.ForeignKey('mocktest.MockTest', on_delete=models.SET_NULL, 
                                    null=True, blank=True, related_name='notifications')
    related_session = models.ForeignKey('mocktest.MockSession', on_delete=models.SET_NULL, 
                                       null=True, blank=True, related_name='session_notifications')
    related_practice = models.ForeignKey('mcqs.TestSession', on_delete=models.SET_NULL, 
                                        null=True, blank=True, related_name='notifications')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type} for {self.user.username}"
    
    def mark_read(self):
        self.is_read = True
        self.save()

class State(models.Model):
    """Model to represent Indian states and union territories"""
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class MedicalCollege(models.Model):
    """Model to store medical college information"""
    OWNERSHIP_CHOICES = [
        ('government_india', 'Government of India'),
        ('government_state', 'State Government'),
        ('private', 'Private'),
        ('autonomous', 'Autonomous'),
    ]
    
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='colleges')
    established = models.IntegerField(help_text="Year of establishment")
    university = models.CharField(max_length=255)
    ownership = models.CharField(max_length=50, choices=OWNERSHIP_CHOICES)
    
    def __str__(self):
        return f"{self.name}, {self.location}, {self.state}"
    
    class Meta:
        ordering = ['state', 'name']
        verbose_name = "Medical College"
        verbose_name_plural = "Medical Colleges"



class AppVersion(models.Model):
    """
    Controls app version and force update mechanism
    """
    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]
    
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, unique=True)
    current_version = models.CharField(max_length=20, help_text="e.g., 1.2.0")
    minimum_version = models.CharField(max_length=20, help_text="Minimum version required to run")
    
    # APK file upload field
    apk_file = models.FileField(
        upload_to='apk/', 
        null=True, 
        blank=True,
        help_text="Upload APK file directly (optional - will use this instead of download_url if provided)"
    )
    
    download_url = models.URLField(
        blank=True, 
        null=True,
        help_text="External URL to download APK (used if apk_file is not provided)"
    )
    
    force_update = models.BooleanField(default=False, help_text="Force users to update")
    update_message = models.TextField(
        default="A new version is available! Please update for the best experience.",
        help_text="Message shown to users"
    )
    whats_new = models.TextField(blank=True, help_text="Release notes")
    is_maintenance = models.BooleanField(default=False, help_text="Enable maintenance mode")
    maintenance_message = models.TextField(
        default="App is under maintenance. Please try again later.",
        blank=True
    )
    
    # Download banner settings
    show_download_banner = models.BooleanField(
        default=True, 
        help_text="Display download banner on landing page"
    )
    banner_text = models.CharField(
        max_length=200,
        default="Download MCQwave Android App - Practice Offline!",
        help_text="Banner text shown to users"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "App Version"
        verbose_name_plural = "App Versions"
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.get_platform_display()} - v{self.current_version}"
    
    def get_download_link(self):
        """Return the appropriate download link (file or URL)"""
        if self.apk_file:
            return self.apk_file.url
        return self.download_url or '#'
    
    @staticmethod
    def compare_versions(version1, version2):
        """
        Compare two version strings
        Returns: 1 if version1 > version2, -1 if version1 < version2, 0 if equal
        """
        v1_parts = [int(x) for x in version1.split('.')]
        v2_parts = [int(x) for x in version2.split('.')]
        
        # Pad with zeros if needed
        while len(v1_parts) < len(v2_parts):
            v1_parts.append(0)
        while len(v2_parts) < len(v1_parts):
            v2_parts.append(0)
        
        for i in range(len(v1_parts)):
            if v1_parts[i] > v2_parts[i]:
                return 1 
            elif v1_parts[i] < v2_parts[i]:
                return -1
        return 0
