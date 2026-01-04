import django
import os
import random

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from mcqs.models import Subject, MCQ  # Replace with your actual app and models

def shuffle_mcq_options(subject_name):
    # Find the subject
    try:
        subject = Subject.objects.get(name=subject_name)
    except Subject.DoesNotExist:
        print(f"Subject '{subject_name}' not found.")
        return

    # Get all MCQs for this subject
    mcqs = MCQ.objects.filter(topic__chapter__unit__subject=subject)

    # Shuffle options for each MCQ
    for mcq in mcqs:
        # Store original options
        options = [
            mcq.option_1, 
            mcq.option_2, 
            mcq.option_3, 
            mcq.option_4
        ]

        # Shuffle the order of options
        shuffled_options = options.copy()
        random.shuffle(shuffled_options)

        # Update MCQ with shuffled options
        mcq.option_1 = shuffled_options[0]
        mcq.option_2 = shuffled_options[1]
        mcq.option_3 = shuffled_options[2]
        mcq.option_4 = shuffled_options[3]

        # Save the updated MCQ
        mcq.save()

    print(f"Options shuffled for all MCQs in subject '{subject_name}'")

# Example usage
if __name__ == '__main__':
    subject_name = input("Enter the subject name: ")
    shuffle_mcq_options(subject_name)