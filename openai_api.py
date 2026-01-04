import os
import django
import openai
import json
from django.db import transaction

# Setup Django environment (Update with your Django project settings)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
django.setup()

from mcqs.models import MCQ, Subject  # Replace 'mcqs' with your actual Django app name

# Set your OpenAI API key
client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Use the latest OpenAI client
# Function to get correct answer and detailed explanation from OpenAI
def update_mcq_with_ai(mcq):
    prompt = f"""
    You are an AI expert in multiple-choice questions. Below is a question with 4 possible answers.
    
    **Question:** {mcq.text}

    **Options:**
    1) {mcq.option_1}
    2) {mcq.option_2}
    3) {mcq.option_3}
    4) {mcq.option_4}

    **Task:**
    - Identify the correct answer (must match exactly with one of the given options).
    - Provide a detailed explanation for the correct answer.

    **Response Format (JSON):**
    {{
        "correct_answer": "Exact text of the correct option",
        "explanation": "Detailed explanation..."
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",  # Use "gpt-3.5-turbo" if needed
            messages=[{"role": "system", "content": "You are an MCQ expert."},
                      {"role": "user", "content": prompt}],
            temperature=0.5
        )

        result = response.choices[0].message.content  # Updated to match new API structure
        response_data = json.loads(result)
        
        return response_data.get("correct_answer"), response_data.get("explanation")
    
    except Exception as e:
        print(f"Error processing MCQ {mcq.uid}: {str(e)}")  # Updated from mcq.id to mcq.uid
        return None, None

# Function to update MCQs for a specific subject
def update_mcqs_for_subject(subject_name, limit=10):
    try:
        subject = Subject.objects.get(name=subject_name)  # Fetch the subject
        mcqs = MCQ.objects.filter(topic__chapter__unit__subject=subject)[:limit]

        if not mcqs:
            print(f"No MCQs found for subject: {subject_name}")
            return

        updated_count = 0

        with transaction.atomic():
            for mcq in mcqs:
                new_answer, new_explanation = update_mcq_with_ai(mcq)
                if new_answer and new_explanation:
                    if new_answer in [mcq.option_1, mcq.option_2, mcq.option_3, mcq.option_4]:
                        mcq.correct_option = new_answer  # Update correct answer
                        mcq.explanation = new_explanation  # Update explanation
                        mcq.save()
                        updated_count += 1
                    else:
                        print(f"Skipping MCQ {mcq.uid} - AI answer not matching any options")  # Updated from mcq.id to mcq.uid

        print(f"Updated {updated_count} MCQs for subject '{subject_name}' successfully.")

    except Subject.DoesNotExist:
        print(f"Subject '{subject_name}' not found!")

# Run the script
if __name__ == "__main__":
    subject_to_update = input("Enter subject name: ")  # Get subject name from user
    update_mcqs_for_subject(subject_to_update, limit=5)  # Change limit to process more
