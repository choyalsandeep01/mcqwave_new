from django.db.models import Count, Q
from typing import Dict, List, Optional
import os
import django
from collections import defaultdict
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()
from mcqs.models import Subject, Unit, Chapter, Topic, difficulties, mcq_types, MCQ

def write_mcq_statistics_to_file():
    """
    Creates a detailed text file with complete MCQ statistics
    Including all subjects, units, chapters, and topics regardless of MCQ count
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"mcq_statistics_{timestamp}.txt"
    
    with open(filename, 'w', encoding='utf-8') as f:
        # Write header
        f.write("=== MCQ Statistics Report ===\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Overall statistics
        total_mcqs = MCQ.objects.count()
        total_pyqs = MCQ.objects.filter(pyq=True).count()
        f.write(f"Total MCQs: {total_mcqs:,}\n")
        f.write(f"Total PYQs: {total_pyqs:,}\n\n")
        
        # Difficulty breakdown
        f.write("=== Difficulty Distribution ===\n")
        difficulty_stats = dict(
            MCQ.objects.values('difficulty__name')
            .exclude(difficulty__isnull=True)
            .annotate(count=Count('uid'))
            .values_list('difficulty__name', 'count')
        )
        for diff, count in difficulty_stats.items():
            f.write(f"{diff}: {count:,} MCQs\n")
        f.write("\n")
        
        # Type breakdown
        f.write("=== MCQ Types Distribution ===\n")
        type_stats = dict(
            MCQ.objects.values('types__types')
            .exclude(types__isnull=True)
            .annotate(count=Count('uid'))
            .values_list('types__types', 'count')
        )
        for mcq_type, count in type_stats.items():
            f.write(f"{mcq_type}: {count:,} MCQs\n")
        f.write("\n")
        
        # Detailed breakdown by subject hierarchy
        f.write("=== Detailed Subject Hierarchy Breakdown ===\n")
        subjects = Subject.objects.prefetch_related(
            'units',
            'units__chapters',
            'units__chapters__topics',
            'units__chapters__topics__topics'
        ).all()
        
        for subject in subjects:
            subject_mcqs = MCQ.objects.filter(topic__chapter__unit__subject=subject)
            subject_count = subject_mcqs.count()
            f.write(f"\nSubject: {subject.name} ({subject_count:,} MCQs)\n")
            
            for unit in subject.units.all():
                unit_mcqs = subject_mcqs.filter(topic__chapter__unit=unit)
                unit_count = unit_mcqs.count()
                f.write(f"  └─ Unit: {unit.name} ({unit_count:,} MCQs)\n")
                
                for chapter in unit.chapters.all():
                    chapter_mcqs = unit_mcqs.filter(topic__chapter=chapter)
                    chapter_count = chapter_mcqs.count()
                    f.write(f"     └─ Chapter: {chapter.name} ({chapter_count:,} MCQs)\n")
                    
                    for topic in chapter.topics.all():
                        topic_mcqs = topic.topics.all()
                        topic_count = topic_mcqs.count()
                        f.write(f"        └─ Topic: {topic.name} ({topic_count:,} MCQs)\n")
                        
                        # Difficulty breakdown for topic
                        difficulty_breakdown = dict(
                            topic_mcqs.values('difficulty__name')
                            .exclude(difficulty__isnull=True)
                            .annotate(count=Count('uid'))
                            .values_list('difficulty__name', 'count')
                        )
                        if difficulty_breakdown:
                            f.write("           Difficulties: " + 
                                  ', '.join(f"{k}: {v}" for k, v in difficulty_breakdown.items()) + 
                                  "\n")
                        
                        # Type breakdown for topic
                        type_breakdown = dict(
                            topic_mcqs.values('types__types')
                            .exclude(types__isnull=True)
                            .annotate(count=Count('uid'))
                            .values_list('types__types', 'count')
                        )
                        if type_breakdown:
                            f.write("           Types: " + 
                                  ', '.join(f"{k}: {v}" for k, v in type_breakdown.items()) + 
                                  "\n")
        
        f.write("\n=== End of Report ===\n")
    
    print(f"Statistics have been written to {filename}")
    return filename

if __name__ == "__main__":
    write_mcq_statistics_to_file()