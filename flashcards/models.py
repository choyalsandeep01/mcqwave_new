from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid


class Subject(models.Model):
    """Medical subjects like Anatomy, Physiology, etc."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    icon = models.CharField(max_length=50, default='book')
    color = models.CharField(max_length=7, default='#3b82f6')
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'name']
        db_table = 'flashcards_subject'
    
    def __str__(self):
        return self.name


class Unit(models.Model):
    """Units within subjects"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='units')
    name = models.CharField(max_length=200)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'name']
        db_table = 'flashcards_unit'
        unique_together = ['subject', 'name']
    
    def __str__(self):
        return f"{self.subject.name} - {self.name}"


class Topic(models.Model):
    """Topics within units"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=200)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['display_order', 'name']
        db_table = 'flashcards_topic'
        unique_together = ['unit', 'name']
    
    def __str__(self):
        return f"{self.unit.name} - {self.name}"


class Flashcard(models.Model):
    """Individual flashcards with spaced repetition metadata"""
    
    TYPE_CHOICES = [
        ('clinical', 'Clinical Case'),
        ('concept', 'Concept'),
        ('image', 'Image-based'),
        ('mnemonic', 'Mnemonic'),
        ('integrated', 'Integrated MCQ'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('moderate', 'Moderate'),
        ('hard', 'Hard'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='flashcards')
    
    # Content
    card_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='concept')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='moderate')
    
    # Front and back content
    front_text = models.TextField(help_text="Question/Prompt")
    back_text = models.TextField(help_text="Answer/Explanation")
    
    # Optional fields
    front_image = models.ImageField(upload_to='flashcards/images/', null=True, blank=True)
    back_image = models.ImageField(upload_to='flashcards/images/', null=True, blank=True)
    mnemonic = models.TextField(null=True, blank=True)
    key_points = models.JSONField(default=list, blank=True)  # List of bullet points
    references = models.TextField(null=True, blank=True)
    
    # Linked MCQs
    linked_mcq_uids = models.JSONField(default=list, blank=True)  # List of MCQ UUIDs
    
    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['topic', 'difficulty', 'created_at']
        db_table = 'flashcards_flashcard'
        indexes = [
            models.Index(fields=['topic', 'card_type']),
            models.Index(fields=['difficulty']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.topic.name} - {self.card_type} - {self.front_text[:50]}"


class UserFlashcardProgress(models.Model):
    """Track individual user progress on each flashcard using SM-2 algorithm"""
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('learning', 'Learning'),
        ('reviewed', 'Reviewed'),
        ('mastered', 'Mastered'),
    ]
    
    RATING_CHOICES = [
        (0, 'Complete Blackout'),
        (1, 'Incorrect - Correct Seemed Easy'),
        (2, 'Incorrect - Remembered with Difficulty'),
        (3, 'Correct - Serious Difficulty'),
        (4, 'Correct - Hesitation'),
        (5, 'Perfect Response'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flashcard_progress')
    flashcard = models.ForeignKey(Flashcard, on_delete=models.CASCADE, related_name='user_progress')
    
    # SM-2 Algorithm fields
    ease_factor = models.FloatField(default=2.5)  # Minimum 1.3
    repetitions = models.IntegerField(default=0)
    interval = models.IntegerField(default=0)  # Days until next review
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    last_rating = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    
    # Bookmarking
    is_bookmarked = models.BooleanField(default=False)
    
    # Notes
    user_note = models.TextField(null=True, blank=True)
    
    # Timestamps
    last_reviewed = models.DateTimeField(null=True, blank=True)
    next_review = models.DateTimeField(default=timezone.now)
    
    # Stats
    total_reviews = models.IntegerField(default=0)
    correct_reviews = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'flashcards_user_progress'
        unique_together = ['user', 'flashcard']
        indexes = [
            models.Index(fields=['user', 'next_review']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['next_review']),
            models.Index(fields=['user', 'is_bookmarked']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.flashcard} - {self.status}"
    
    def update_sm2(self, quality):
        """
        SM-2 Spaced Repetition Algorithm
        quality: 0-5 (user rating)
        """
        self.total_reviews += 1
        self.last_reviewed = timezone.now()
        self.last_rating = quality
        
        if quality >= 3:
            self.correct_reviews += 1
        
        # Calculate new ease factor
        self.ease_factor = max(1.3, self.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        
        # Reset repetitions if quality < 3
        if quality < 3:
            self.repetitions = 0
            self.interval = 1
            self.status = 'learning'
        else:
            if self.repetitions == 0:
                self.interval = 1
            elif self.repetitions == 1:
                self.interval = 6
            else:
                self.interval = int(self.interval * self.ease_factor)
            
            self.repetitions += 1
            
            # Update status based on performance
            if self.repetitions >= 5 and self.ease_factor >= 2.5:
                self.status = 'mastered'
            elif self.repetitions >= 2:
                self.status = 'reviewed'
            else:
                self.status = 'learning'
        
        # Calculate next review date
        self.next_review = timezone.now() + timedelta(days=self.interval)
        self.save()
    
    @property
    def is_due(self):
        """Check if card is due for review"""
        return timezone.now() >= self.next_review
    
    @property
    def accuracy(self):
        """Calculate accuracy percentage"""
        if self.total_reviews == 0:
            return 0
        return (self.correct_reviews / self.total_reviews) * 100


class UserStreak(models.Model):
    """Track daily study streaks for gamification"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='flashcard_streak')
    
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_study_date = models.DateField(null=True, blank=True)
    
    total_xp = models.IntegerField(default=0)
    total_cards_studied = models.IntegerField(default=0)
    
    # Daily goal
    daily_goal = models.IntegerField(default=20)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'flashcards_user_streak'
    
    def update_streak(self):
        """Update streak when user studies"""
        today = timezone.now().date()
        
        if self.last_study_date == today:
            return  # Already studied today
        
        if self.last_study_date == today - timedelta(days=1):
            self.current_streak += 1
        elif self.last_study_date is None or self.last_study_date < today - timedelta(days=1):
            self.current_streak = 1
        
        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak
        
        self.last_study_date = today
        self.save()


class Badge(models.Model):
    """Achievement badges for gamification"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#fbbf24')
    
    # Criteria
    criteria_type = models.CharField(max_length=50)  # e.g., 'streak', 'cards_mastered', 'subject_complete'
    criteria_value = models.IntegerField()
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    
    xp_reward = models.IntegerField(default=100)
    
    class Meta:
        db_table = 'flashcards_badge'
    
    def __str__(self):
        return self.name


class UserBadge(models.Model):
    """Badges earned by users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flashcard_badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'flashcards_user_badge'
        unique_together = ['user', 'badge']
        ordering = ['-earned_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"


class StudySession(models.Model):
    """Track individual study sessions"""
    SESSION_MODES = [
        ('today', 'Today\'s Session'),
        ('topic', 'Topic Focus'),
        ('weak', 'Weak Topics'),
        ('mixed', 'Mixed Review'),
        ('custom', 'Custom Session'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flashcard_study_sessions')
    
    mode = models.CharField(max_length=20, choices=SESSION_MODES, default='today')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    
    cards_reviewed = models.IntegerField(default=0)
    cards_correct = models.IntegerField(default=0)
    
    duration_seconds = models.IntegerField(default=0)
    xp_earned = models.IntegerField(default=0)
    
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'flashcards_study_session'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.mode} - {self.started_at.strftime('%Y-%m-%d')}"
