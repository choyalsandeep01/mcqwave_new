from django.db import models
from base.models import BaseModel
from uuid import UUID
import uuid
from django.contrib.auth.models import User
from django.utils import timezone

# Simple choices
PYQ_Cat = [
    ('NEET-PG', 'NEET-PG'),
    ('INI-CET', 'INI-CET'),
    ('FMGE', 'FMGE'),
    ('UPSC-CMS', 'UPSC-CMS')
]

YEAR_CHOICES = [(str(year), str(year)) for year in range(2000, 2026)]
YEAR_CHOICES = [('', '--------')] + YEAR_CHOICES

# Month choices for exams that happen multiple times per year
MONTH_CHOICES = [
    ('', '--------'),
    ('January', 'January'),
    ('February', 'February'),
    ('March', 'March'),
    ('April', 'April'),
    ('May', 'May'),
    ('June', 'June'),
    ('July', 'July'),
    ('August', 'August'),
    ('September', 'September'),
    ('October', 'October'),
    ('November', 'November'),
    ('December', 'December'),
]

MCQ_TYPES = [
    ('General', 'General'),
    ('Image', 'Image'),
    ('Clinical', 'Clinical'),
]

DIFFICULTY_CHOICES = [
    ('Easy', 'Easy'),
    ('Medium', 'Medium'),
    ('Tough', 'Tough'),
]

SUBJECT_ICON_CHOICES = [
    ('fas fa-heart', 'Heart - Cardiology/Medicine'),
    ('fas fa-brain', 'Brain - Neurology/Psychiatry'),
    ('fas fa-bone', 'Bone - Orthopedics'),
    ('fas fa-lungs', 'Lungs - Respiratory Medicine'),
    ('fas fa-eye', 'Eye - Ophthalmology'),
    ('fas fa-tooth', 'Tooth - Dentistry'),
    ('fas fa-baby', 'Baby - Pediatrics'),
    ('fas fa-female', 'Female - Gynecology'),
    ('fas fa-male', 'Male - Andrology'),
    ('fas fa-cut', 'Cut - Surgery'),
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
        ordering = ['subject', 'order']


class difficulties(BaseModel):
    name = models.CharField(max_length=255)
    
    def __str__(self):
        return self.name


class mcq_types(BaseModel):
    types = models.CharField(max_length=255)
    
    def __str__(self):
        return self.types


class PYQ(BaseModel):
    bulk_input = models.TextField(blank=True, null=True)
    
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='pyqs', null=True)
    topic = models.CharField(max_length=255, blank=True, null=True, help_text="Topic name for this question")

    text = models.TextField(default='Default question text')
    option_1 = models.CharField(max_length=255, blank=True, null=True)
    option_2 = models.CharField(max_length=255, blank=True, null=True)
    option_3 = models.CharField(max_length=255, blank=True, null=True)
    option_4 = models.CharField(max_length=255, blank=True, null=True)
    correct_option = models.CharField(max_length=255, blank=True, null=True)
    explanation = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='pyq_images/', blank=True, null=True)
    correct_attempts = models.IntegerField(default=0)
    incorrect_attempts = models.IntegerField(default=0)
    
    difficulty = models.ForeignKey(difficulties, on_delete=models.CASCADE, related_name='pyq_difficulty', blank=True, null=True)
    types = models.ForeignKey(mcq_types, on_delete=models.CASCADE, related_name='pyq_type', blank=True, null=True)
    pyqcode = models.CharField(max_length=255, blank=True, null=True)
    hig_yield = models.BooleanField(default=False)
    pyq = models.BooleanField(default=True)
    pyq_cat = models.CharField(max_length=100, choices=PYQ_Cat, blank=True, null=True)
    pyq_year = models.CharField(max_length=4, choices=YEAR_CHOICES, blank=True, default='')
    pyq_month = models.CharField(
        max_length=20, 
        choices=MONTH_CHOICES, 
        blank=True, 
        default='',
        help_text="Optional: Month for exams that occur multiple times per year (e.g., INI-CET, FMGE)"
    )

    def __str__(self):
        return self.text
    
    def get_exam_display(self):
        """Returns formatted exam display with month if available"""
        if not self.pyq_cat:
            return ""
        
        display = self.pyq_cat
        
        # Add month for exams that happen multiple times per year
        if self.pyq_month and self.pyq_cat in ['INI-CET', 'FMGE']:
            display += f" {self.pyq_month}"
        
        # Add year if available
        if self.pyq_year:
            display += f" {self.pyq_year}"
            
        return display
    
    def save(self, *args, **kwargs):
        if self.bulk_input:
            parts = self.bulk_input.split('|')
            if len(parts) == 7:
                self.text = parts[0]
                self.option_1 = parts[1]
                self.option_2 = parts[2]
                self.option_3 = parts[3]
                self.option_4 = parts[4]
                self.correct_option = parts[5]
                self.explanation = parts[6]
            self.bulk_input = ''
        
        super(PYQ, self).save(*args, **kwargs)


class PYQBookmark(BaseModel):
    TYPE_CHOICES = [
        ('Star', 'Star'),
        ('Unstudied', 'Unstudied'),
        ('Other', 'Other')
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bkmk_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    pyq = models.ForeignKey(PYQ, on_delete=models.CASCADE)
    test_session = models.ForeignKey('mcqs.TestSession', on_delete=models.CASCADE)
    bookmark_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'pyq', 'test_session')
        ordering = ['-created_at']

    def __str__(self):
        return f"PYQ Bookmark: {self.user.username} - {self.pyq.text[:50]}... - {self.bookmark_type}"




from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
@receiver([post_save, post_delete], sender=PYQ)
def clear_pyq_cache(sender, **kwargs):
    """Clear PYQ selection cache when PYQs change"""
    cache.delete('pyq_selection_data_v1')
