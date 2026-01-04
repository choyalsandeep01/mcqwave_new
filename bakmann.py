#!/usr/bin/env python
"""
Script to update MCQ explanations that contain "**[Backmann Nad Lings Obstetrics And Gynecology]**"
and replace with "[Beckmann and Ling's Obstetrics and Gynecology]"
"""

import os
import re
import django
import sys

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")  # Replace with your project name
django.setup()

# Import your models (will work after django.setup())
from django.db.models import Q
from base.models import BaseModel  # Make sure this path is correct
# Import your app's models
from mcqs.models import MCQ, Subject, Topic, Chapter, Unit  # Replace 'your_app' with your app name

def update_mcq_explanations(subject_name=None):
    """
    Find MCQs whose explanations contain "**[Backmann Nad Lings Obstetrics And Gynecology]**"
    and update it to "[Beckmann and Ling's Obstetrics and Gynecology]"
    
    Args:
        subject_name (str, optional): If provided, only search MCQs from this subject
    """
    # The text to search for and its replacement
    search_text = r"\*\*\[Backmann Nad Lings Obstetrics And Gynecology\]\*\*"
    replacement_text = "[Beckmann and Ling's Obstetrics and Gynecology]"
    
    # Base query to find MCQs with matching text in explanation
    mcq_query = MCQ.objects.filter(
        explanation__icontains="Backmann Nad Lings Obstetrics And Gynecology"
    )
    
    # If subject name is provided, filter by subject
    if subject_name:
        print(f"Filtering by subject: {subject_name}")
        # Get the subject
        try:
            subject = Subject.objects.get(name=subject_name)
            # Find all units for this subject
            units = Unit.objects.filter(subject=subject)
            # Find all chapters for these units
            chapters = Chapter.objects.filter(unit__in=units)
            # Find all topics for these chapters
            topics = Topic.objects.filter(chapter__in=chapters)
            # Filter MCQs by these topics
            mcq_query = mcq_query.filter(topic__in=topics)
        except Subject.DoesNotExist:
            print(f"Subject '{subject_name}' not found. No MCQs were updated.")
            return
    
    # Get matching MCQs
    mcqs_to_update = mcq_query.all()
    print(f"Found {mcqs_to_update.count()} MCQs that might need updating.")
    
    # Track which MCQs were updated
    updated_count = 0
    
    # Update each matching MCQ
    for mcq in mcqs_to_update:
        if mcq.explanation:
            # Use regex to ensure we only replace the exact pattern
            new_explanation = re.sub(search_text, replacement_text, mcq.explanation)
            
            # Also try without the asterisks in case formatting varies
            alternate_search = r"\[Backmann Nad Lings Obstetrics And Gynecology\]"
            if new_explanation == mcq.explanation:  # If no change with first pattern
                new_explanation = re.sub(alternate_search, replacement_text, mcq.explanation)
            
            # If any changes were made
            if new_explanation != mcq.explanation:
                # Log the change
                print(f"\nUpdating MCQ ID {mcq.uid}:")
                print(f"Original text snippet: '...{mcq.explanation[-100:]}'")
                
                # Update the explanation
                mcq.explanation = new_explanation
                mcq.save()
                
                print(f"Updated text snippet: '...{new_explanation[-100:]}'")
                updated_count += 1
    
    print(f"\nSummary: Updated {updated_count} MCQ explanation(s) out of {mcqs_to_update.count()} checked")

if __name__ == "__main__":
    # Get subject name from command line argument if provided
    subject_name = None
    if len(sys.argv) > 1:
        subject_name = sys.argv[1]
        
    print("Starting MCQ explanation update script...")
    print("This script will update explanations containing '**[Backmann Nad Lings Obstetrics And Gynecology]**'")
    print("to '[Beckmann and Ling's Obstetrics and Gynecology]'")
    
    # Run the update function
    update_mcq_explanations(subject_name)
    
    print("\nScript completed.")