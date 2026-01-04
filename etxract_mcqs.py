import os
import django
from django.conf import settings

# Setup Django environment (Modify settings accordingly if needed)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()
from mcqs.models import MCQ, Subject  # Replace `mcq_app` with your actual app name

def export_mcqs_by_subject(subject_name):
    try:
        # Get the subject
        subject = Subject.objects.get(name=subject_name)
        
        # Fetch all MCQs related to the subject
        mcqs = MCQ.objects.filter(topic__chapter__unit__subject=subject)

        if not mcqs.exists():
            print(f"No MCQs found for subject: {subject_name}")
            return
        
        # Define file path
        file_name = f"{subject_name.replace(' ', '_')}_MCQs.txt"
        file_path = os.path.join(settings.BASE_DIR, file_name)

        with open(file_path, "w", encoding="utf-8") as file:
            for mcq in mcqs:
                file.write(f"UID: {mcq.uid}\n")
                file.write(f"Question: {mcq.text}\n")
                file.write(f"1. {mcq.option_1}\n")
                file.write(f"2. {mcq.option_2}\n")
                file.write(f"3. {mcq.option_3}\n")
                file.write(f"4. {mcq.option_4}\n")
                file.write(f"Correct Option: {mcq.correct_option}\n")
                file.write(f"Explanation: {mcq.explanation}\n")
                file.write("-" * 50 + "\n")  # Separator between MCQs
        
        print(f"MCQs for '{subject_name}' exported successfully to {file_path}")

    except Subject.DoesNotExist:
        print(f"Subject '{subject_name}' not found.")

if __name__ == "__main__":
    subject_name = input("Enter the subject name: ")
    export_mcqs_by_subject(subject_name)
