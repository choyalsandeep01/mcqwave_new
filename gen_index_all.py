import os
import django
from django.db.models import Prefetch

# Setup Django environment (you may need to adjust these settings)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

# Import models (adjust the import path as needed)
from mcqs.models import Subject, Unit, Chapter, Topic

def generate_index():
    """Generate a hierarchical index of all subjects, units, chapters, and topics."""
    
    output_path = "subject_index.txt"
    
    # Fetch all data with optimized queries to avoid N+1 problem
    subjects = Subject.objects.all().prefetch_related(
        Prefetch('units', queryset=Unit.objects.all().prefetch_related(
            Prefetch('chapters', queryset=Chapter.objects.all().prefetch_related(
                'topics'
            ))
        ))
    )
    
    with open(output_path, 'w') as f:
        f.write("COMPLETE SUBJECT INDEX\n")
        f.write("=====================\n\n")
        
        for subject_idx, subject in enumerate(subjects, 1):
            f.write(f"{subject_idx}. {subject.name}\n")
            
            for unit_idx, unit in enumerate(subject.units.all(), 1):
                f.write(f"   {subject_idx}.{unit_idx}. Unit: {unit.name}\n")
                
                for chapter_idx, chapter in enumerate(unit.chapters.all(), 1):
                    f.write(f"      {subject_idx}.{unit_idx}.{chapter_idx}. Chapter: {chapter.name}\n")
                    
                    for topic_idx, topic in enumerate(chapter.topics.all(), 1):
                        f.write(f"         {subject_idx}.{unit_idx}.{chapter_idx}.{topic_idx}. Topic: {topic.name}\n")
            
            f.write("\n")  # Extra line between subjects for readability
    
    print(f"Index successfully generated and saved to {output_path}")
    
    # Bonus: Also generate a summary count
    total_units = sum(subject.units.count() for subject in subjects)
    total_chapters = sum(unit.chapters.count() for subject in subjects for unit in subject.units.all())
    total_topics = sum(chapter.topics.count() for subject in subjects for unit in subject.units.all() for chapter in unit.chapters.all())
    
    with open("index_summary.txt", 'w') as f:
        f.write("INDEX SUMMARY\n")
        f.write("=============\n\n")
        f.write(f"Total Subjects: {subjects.count()}\n")
        f.write(f"Total Units: {total_units}\n")
        f.write(f"Total Chapters: {total_chapters}\n")
        f.write(f"Total Topics: {total_topics}\n")
    
    print("Summary stats also generated in index_summary.txt")

if __name__ == "__main__":
    generate_index()