from django.db import models
from base.models import BaseModel
# Create your models here.
from uuid import UUID
import uuid

from django.db import models
from django.utils import timezone
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
PYQ_Cat = [
    ('NEET-PG Pattern', 'NEET PG Pattern'),
    ('INI-CET', 'INI-CET'),
    ('FMGE', 'FMGE'),
]
YEAR_CHOICES = [(str(year), str(year)) for year in range(2000, 2026)]
YEAR_CHOICES = [('', '--------')] + YEAR_CHOICES
SUBJECT_ICON_CHOICES = [
    ('fas fa-heart nfas', 'Heart - Cardiology/Medicine'),
    ('fas fa-brain', 'Brain - Neurology/Psychiatry'),
    ('fas fa-bone', 'Bone - Orthopedics'),
    ('fas fa-lungs', 'Lungs - Respiratory Medicine'),
    ('fas fa-eye', 'Eye - Ophthalmology'),
    ('fas fa-tooth', 'Tooth - Dentistry'),
    ('fas fa-baby', 'Baby - Pediatrics'),
    ('fas fa-female', 'Female - Gynecology'),
    ('fas fa-male', 'Male - Andrology'),
    ('fas fa-cut nfas', 'Cut - Surgery'),
    ('fas fa-pills', 'Pills - Pharmacology'),
    ('fas fa-microscope', 'Microscope - Pathology'),
    ('fas fa-dna', 'DNA - Genetics/Biochemistry'),
    ('fas fa-virus', 'Virus - Microbiology'),
    ('fas fa-radiation', 'Radiation - Radiology'),
    ('fas fa-syringe', 'Syringe - Anesthesia'),
    ('fas fa-user-md', 'Doctor - General Medicine'),
    ('fas fa-stethoscope', 'Stethoscope - General'),
    ('fas fa-heartbeat', 'Heartbeat - Physiology'),
    ('fas fa-flask', 'Flask - Biochemistry'),
    ('fas fa-notes-medical', 'Medical Notes - Medicine'),
    ('fas fa-x-ray', 'X-Ray - Radiology'),
    ('fas fa-ambulance', 'Ambulance - Emergency Medicine'),
    ('fas fa-hand-holding-medical', 'Hand Medical - General Care'),
    ('fas fa-clinic-medical', 'Clinic - General Medicine'),
]

class Subject(BaseModel):
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255)
    icon = models.CharField(
        max_length=50, 
        choices=SUBJECT_ICON_CHOICES, 
        default='fas fa-stethoscope',
        help_text="FontAwesome icon class for this subject"
    )
    icon_color = models.CharField(
        max_length=20, 
        default='#1e3c72',
        help_text="Hex color code for the icon (e.g., #007bff)"
    )
    def __str__(self):
        return self.name

    class Meta:
        ordering = ['order']

    def get_icon_html(self):
        """Returns HTML for displaying the icon"""
        return f'<i class="{self.icon}" style="color: {self.icon_color};"></i>'






class Unit(BaseModel):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='units')
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.subject.name} - Unit {self.name}"
    class Meta:
        ordering = ['subject','order']

        
class Chapter(BaseModel):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='chapters')
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255)
    
    def __str__(self):
        return f"{self.unit.subject.name} - Unit {self.unit.name} - Chapter {self.name}"
    class Meta:
        ordering = ['order']


class Topic(BaseModel):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='topics')
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.chapter.unit.subject.name} - Unit {self.chapter.unit.name} - Chapter {self.chapter.name} - Topic {self.name}"
    class Meta:
        ordering = ['order']


class difficulties(BaseModel):
    
    name = models.CharField(max_length=255)
    def __str__(self):
        return self.name
    
class mcq_types(BaseModel):
    
    types = models.CharField(max_length=255)
    def __str__(self):
        return self.types

class MCQ(BaseModel):
    bulk_input = models.TextField(blank=True,null=True)

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='topics',null=True)
    text = models.TextField(default='Default question text')
    option_1 = models.CharField(max_length=255,blank=True, null=True)
    option_2 = models.CharField(max_length=255,blank=True, null=True)
    option_3 = models.CharField(max_length=255,blank=True, null=True)
    option_4 = models.CharField(max_length=255,blank=True, null=True)
    correct_option = models.CharField(max_length=255,blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='mcq_images/', blank=True, null=True)
    correct_attempts = models.IntegerField(default=0)
    incorrect_attempts = models.IntegerField(default=0)
    
    difficulty = models.ForeignKey(difficulties, on_delete=models.CASCADE,related_name='difficulty',blank=True, null=True)
    types = models.ForeignKey(mcq_types, on_delete=models.CASCADE, related_name='type',blank=True, null=True)
    mcqcode = models.CharField(max_length=255,blank=True, null=True)
    hig_yield = models.BooleanField(default=False)
    pyq = models.BooleanField(default=False)
    pyq_cat = models.CharField(max_length=100, choices=PYQ_Cat, blank=True, null=True)
    pyq_year = models.CharField(max_length=4, choices=YEAR_CHOICES, blank=True, default='')

    def __str__(self):
        return self.text
    
    def save(self,*args, **kwargs):
        if self.bulk_input:
            parts = self.bulk_input.split('|')
            if len(parts)==7:
                    self.text=parts[0]
                    self.option_1=parts[1]
                    self.option_2=parts[2]
                    self.option_3=parts[3]
                    self.option_4=parts[4]
                    self.correct_option=parts[5]

                    self.explanation=parts[6]
            self.bulk_input = ''

        
        super(MCQ,self).save(*args,**kwargs)

class MCQFeedback(BaseModel):
    mcq = models.ForeignKey(MCQ, on_delete=models.CASCADE, related_name='feedbacks')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    feedback_text = models.TextField()
    feedback_type = models.CharField(max_length=50, choices=[
        ('incorrect_answer', 'Incorrect Answer'),
        ('unclear_question', 'Unclear Question'),
        ('wrong_explanation', 'Wrong Explanation'),
        ('typo', 'Typo/Grammar'),
        ('image_issue', 'Image Issue'),
        ('other', 'Other')
    ])
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected')
    ], default='pending')
    admin_response = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback on MCQ {self.mcq.uid} by {self.user.username}"
from datetime import datetime

class TestSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    test_id = models.CharField(max_length=100, unique=True)  # Unique ID for the test session
     # Remaining time in seconds
    timestamp = models.DateTimeField(auto_now=True)  #t Track when the session was last updaed
    submitted = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(default=timezone.now)
    total_questions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    timetaken = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Track when the session was created
    totaltime = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selections = models.JSONField(default=list)
    mode = models.CharField(max_length=10,blank=True, null=True)
    pyq = models.BooleanField(default=False)
    
    def __str__(self):
        return f"TestSession for {self.user.username} with Test ID {self.test_id}"

class TestAnswer(models.Model):
    test_session = models.ForeignKey(TestSession, on_delete=models.CASCADE)
    mcq_uid = models.UUIDField()  # UID of the MCQ
    selected_option = models.CharField(max_length=10, blank=True, null=True)  # Selected answer option
    timespent = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_attempted = models.BooleanField(default=False)  # Track if the question has been attempted
    selected_optiontext = models.CharField(max_length=255, blank=True, null=True)
    correct = models.BooleanField(default=False)
    def __str__(self):
        return f"Answer for {self.mcq_uid} in Test ID {self.test_session.test_id}"

class Bookmark(models.Model):
    TYPE_CHOICES = [
        ('Star', 'Star'),
        ('Unstudied', 'Unstudied'),
        ('Other', 'Other')
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bkmk_id = models.CharField(max_length=100, unique=True, null=True, blank=True)  # Allowing null and blank
    mcq = models.ForeignKey(MCQ, on_delete=models.CASCADE)
    test_session = models.ForeignKey(TestSession, on_delete=models.CASCADE)
    bookmark_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'mcq', 'test_session')


from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
@receiver([post_save, post_delete], sender=MCQ)
def clear_mcq_cache(sender, **kwargs):
    """Clear cache when MCQs change"""
    cache.delete('mcq_structure_v2')

@receiver([post_save, post_delete], sender=Topic)
def clear_topic_cache(sender, **kwargs):
    """Clear cache when topics change"""
    cache.delete('mcq_structure_v2')

@receiver([post_save, post_delete], sender=Chapter)
def clear_chapter_cache(sender, **kwargs):
    """Clear cache when chapters change"""
    cache.delete('mcq_structure_v2')

@receiver([post_save, post_delete], sender=Unit)
def clear_unit_cache(sender, **kwargs):
    """Clear cache when units change"""
    cache.delete('mcq_structure_v2')

@receiver([post_save, post_delete], sender=Subject)
def clear_subject_cache(sender, **kwargs):
    """Clear cache when subjects change"""
    cache.delete('mcq_structure_v2')
