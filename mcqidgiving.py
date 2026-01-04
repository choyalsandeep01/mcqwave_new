import os
import sys
import django
from django.db.models import Q

# Add your project directory to the Python path
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_dir)

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

# Configure Django
django.setup()

# Now import your models
from mcqs.models import MCQ

def generate_mcq_code(mcq):
    # Extract first letters from hierarchy
    subject_code = mcq.topic.chapter.unit.subject.name[0].upper()
    unit_code = mcq.topic.chapter.unit.name[0].upper()
    chapter_code = mcq.topic.chapter.name[0].upper()
    topic_code = mcq.topic.name[0].upper()
    
    # Find existing codes to ensure uniqueness
    existing_codes = set(MCQ.objects.exclude(Q(mcqcode=None) | Q(mcqcode='')).values_list('mcqcode', flat=True))
    
    # Try random numbers starting from 1
    for random_num in range(1, 10):  # 1-9
        proposed_code = f"{subject_code}{unit_code}{chapter_code}{topic_code}{random_num}"
        
        if proposed_code not in existing_codes:
            return proposed_code
    
    # If all single-digit numbers are taken, extend to two digits
    for random_num in range(10, 100):
        proposed_code = f"{subject_code}{unit_code}{chapter_code}{topic_code}{random_num}"
        
        if proposed_code not in existing_codes:
            return proposed_code
    
    return None  # In case of extremely unlikely scenario

def update_mcq_codes():
    # Get all MCQs without mcqcode
    mcqs_without_code = MCQ.objects.filter(Q(mcqcode=None) | Q(mcqcode=''))
    
    for mcq in mcqs_without_code:
        mcq.mcqcode = generate_mcq_code(mcq)
        mcq.save()

# Run the update
if __name__ == '__main__':
    update_mcq_codes()