import os
import re
import django
import argparse
from openai import OpenAI
from tqdm import tqdm
import logging
import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mcq_explanation_update.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Setup OpenAI client


# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')  # Change this to your project settings
django.setup()

# Import your models after Django setup
from mcqs.models import Subject, Unit, Chapter, Topic, MCQ  # Update with your actual app name

def get_detailed_explanation(mcq):
    """Get a detailed explanation for the MCQ using the API."""
    
    # Format options for prompt
    options = {
        "1": mcq.option_1,
        "2": mcq.option_2,
        "3": mcq.option_3,
        "4": mcq.option_4
    }
    
    # Filter out None or empty options
    options = {k: v for k, v in options.items() if v and v.strip()}
    
    # Format options for prompt
    options_text = "\n".join([f"{num}. {option}" for num, option in options.items()])
    
    # Construct the prompt
    prompt = f"""
I need a detailed and organized explanation for the following medical MCQ:

Question: {mcq.text}
Options:
{options_text}
Correct Answer: {mcq.correct_option}
Current Brief Explanation: {mcq.explanation if mcq.explanation else 'None provided'}
Source: {getattr(mcq, 'mcqcode', 'Not specified')}

Please provide a comprehensive explanation with the following structure:

1. Correct Answer Explanation: Explain why the correct answer is right in a clear, concise manner.

2. For each incorrect option: Explain why it is incorrect (labeled as Option 1, Option 2, etc.)

3. Key Clinical Points: Provide relevant clinical context and important points for healthcare providers in a bullet-point format.

IMPORTANT FORMATTING INSTRUCTIONS:
- Use clean, well-organized bullet points or numbered lists
- Avoid excessive symbols like ###, ***, or --- 
- Use simple formatting like "Correct Answer:" instead of elaborate headers
- Keep explanations clear, concise, and easy to understand
- Make the structure consistent and organized for easy reference
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical education expert specializing in creating well-organized explanations for medical board exam questions. Present information in a clean, structured format with clear bullet points that's easy to understand and reference.",
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-4o",
            temperature=0.7,
            max_tokens=4096,
            top_p=1
        )
        
        # Clean up excessive formatting
        clean_explanation = response.choices[0].message.content
        
        # Remove horizontal divider lines
        clean_explanation = re.sub(r'---+', '', clean_explanation)
        
        # Replace excessive hashtag headers with clean headers
        clean_explanation = re.sub(r'#{1,6}\s+(.*?)\s*$', r'\1:', clean_explanation, flags=re.MULTILINE)
        
        return clean_explanation, None
        
    except Exception as e:
        logger.error(f"Error generating explanation: {str(e)}")
        return None, f"API error: {str(e)}"

def write_log_file(log_entries, subject_name):
    """Write the log entries to a log file."""
    log_file = f"mcq_explanation_update_log_{subject_name.replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    with open(log_file, 'w', encoding='utf-8') as file:
        file.write(f"MCQ Explanation Update Log - {subject_name}\n")
        file.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write("=" * 80 + "\n\n")
        
        file.write(f"Total MCQs Processed: {len(log_entries)}\n")
        updated_count = sum(1 for entry in log_entries if entry['updated'])
        file.write(f"MCQs Updated: {updated_count}\n")
        file.write(f"MCQs Unchanged/Errors: {len(log_entries) - updated_count}\n\n")
        
        file.write("DETAILED LOG:\n")
        file.write("-" * 80 + "\n\n")
        
        for entry in log_entries:
            file.write(f"ID: {entry['id']}\n")
            file.write(f"Topic: {entry['topic']}\n")
            file.write(f"Question: {entry['question'][:150]}...\n" if len(entry['question']) > 150 else f"Question: {entry['question']}\n")
            
            if entry['updated']:
                # Only include a portion of the explanation to keep the log manageable
                explanation_preview = entry['new_explanation'][:200] + "..." if len(entry['new_explanation']) > 200 else entry['new_explanation']
                file.write(f"Explanation Updated: Yes\n")
                file.write(f"New Explanation Preview: {explanation_preview}\n")
            else:
                file.write(f"Explanation Updated: No\n")
                file.write(f"Reason: {entry['status']}\n")
                
            file.write("-" * 50 + "\n\n")
            
    logger.info(f"Log file written to {log_file}")
    return log_file

def update_mcq_explanations_for_subject(subject_name, batch_size=10, dry_run=False, filter_empty=False):
    """
    Update explanations for MCQs in a specific subject.
    
    Args:
        subject_name: Name of the subject to process
        batch_size: Number of MCQs to process in each batch
        dry_run: If True, don't actually update the database
        filter_empty: If True, only process MCQs with empty explanations
    
    Returns:
        Tuple of (updated_count, total_count, log_file_path)
    """
    try:
        # Get the subject
        subject = Subject.objects.get(name=subject_name)
        logger.info(f"Found subject: {subject}")
        
        # Get all MCQs for this subject via the related chain
        mcq_query = MCQ.objects.filter(topic__chapter__unit__subject=subject)
        
        # Optionally filter for MCQs with empty explanations
        if filter_empty:
            mcq_query = mcq_query.filter(explanation__isnull=True) | mcq_query.filter(explanation="")
            
        mcqs = mcq_query
        total_count = mcqs.count()
        
        logger.info(f"Found {total_count} MCQs for subject {subject_name}")
        
        if total_count == 0:
            logger.warning(f"No MCQs found for subject {subject_name}")
            return 0, 0, None
        
        # Process MCQs in batches to avoid memory issues
        log_entries = []
        updated_count = 0
        
        # Use tqdm for progress bar
        for i in tqdm(range(0, total_count, batch_size), desc="Processing batches"):
            batch = mcqs[i:i+batch_size]
            
            for mcq in batch:
                # Skip if any essential option is missing
                if not mcq.option_1 or not mcq.option_2 or not mcq.correct_option:
                    log_entry = {
                        'id': mcq.uid,
                        'topic': str(mcq.topic) if mcq.topic else "No topic",
                        'question': mcq.text,
                        'updated': False,
                        'status': "Skipped - Essential options or correct answer missing",
                        'new_explanation': None
                    }
                    log_entries.append(log_entry)
                    logger.warning(f"Skipping MCQ {mcq.uid} - missing essential data")
                    continue
                
                # Generate a detailed explanation
                new_explanation, error = get_detailed_explanation(mcq)
                
                if new_explanation:
                    # Create log entry
                    log_entry = {
                        'id': mcq.uid,
                        'topic': str(mcq.topic) if mcq.topic else "No topic",
                        'question': mcq.text,
                        'updated': True,
                        'status': "Explanation updated successfully",
                        'new_explanation': new_explanation
                    }
                    log_entries.append(log_entry)
                    
                    # Update the explanation if not a dry run
                    if not dry_run:
                        mcq.explanation = new_explanation
                        mcq.save()
                        updated_count += 1
                        logger.info(f"Updated explanation for MCQ {mcq.uid}")
                else:
                    # Log the error
                    log_entry = {
                        'id': mcq.uid,
                        'topic': str(mcq.topic) if mcq.topic else "No topic",
                        'question': mcq.text,
                        'updated': False,
                        'status': error if error else "Unknown error generating explanation",
                        'new_explanation': None
                    }
                    log_entries.append(log_entry)
                    logger.error(f"Failed to update MCQ {mcq.uid}: {error}")
        
        # Write log file
        log_file = write_log_file(log_entries, subject_name)
        
        logger.info(f"Process complete! {updated_count} explanations updated out of {total_count} questions.")
        if dry_run:
            logger.info("This was a dry run - no actual changes were made to the database.")
            
        return updated_count, total_count, log_file
        
    except Subject.DoesNotExist:
        logger.error(f"Subject '{subject_name}' does not exist")
        return 0, 0, None
    except Exception as e:
        logger.error(f"Error processing subject {subject_name}: {str(e)}")
        return 0, 0, None

def main():
    """
    Main function to run the script.
    """
    parser = argparse.ArgumentParser(description="Update explanations for MCQs in a specific subject")
    parser.add_argument("subject", type=str, help="Name of the subject to process")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of MCQs to process in each batch")
    parser.add_argument("--dry-run", action="store_true", help="Run without making actual changes to the database")
    parser.add_argument("--filter-empty", action="store_true", help="Only process MCQs with empty explanations")
    
    args = parser.parse_args()
    
    logger.info(f"Starting MCQ explanation update for subject: {args.subject}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Filter empty: {args.filter_empty}")
    
    updated_count, total_count, log_file = update_mcq_explanations_for_subject(
        args.subject,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        filter_empty=args.filter_empty
    )
    
    print(f"\nProcess complete!")
    print(f"Subject: {args.subject}")
    print(f"Total MCQs processed: {total_count}")
    print(f"MCQs updated: {updated_count}")
    if log_file:
        print(f"Log file: {log_file}")
    if args.dry_run:
        print("This was a dry run - no actual changes were made to the database.")

if __name__ == "__main__":
    main()