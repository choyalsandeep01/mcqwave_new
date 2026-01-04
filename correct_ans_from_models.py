import os
import re
import django
import datetime
from openai import OpenAI
import logging
from tqdm import tqdm  # For progress bar

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mcq_validation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Setup OpenAI client
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key="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",
)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')  # Change this to your project settings
django.setup()

# Import your models after Django setup
from mcqs.models import Subject, Unit, Chapter, Topic, MCQ  # Update with your actual app name

def normalize_text(text):
    """
    Normalize text for comparison by removing extra spaces and ensuring consistent formatting.
    This function is used for debugging and logging only, not for actual matching.
    """
    if not text:
        return ""
    # Replace multiple spaces with a single space and strip
    return re.sub(r'\s+', ' ', text).strip()

def identify_closest_option(correct_answer, options):
    """
    Identify which option is most similar to the correct answer and prepare a mapping for logging.
    Returns a dict with detailed comparison information.
    """
    comparison_info = {}
    
    for key, value in options.items():
        # Check exact equality
        if correct_answer == value:
            comparison_info[key] = {
                "option_text": value,
                "exact_match": True,
                "differences": None
            }
        else:
            # For logging purposes, show character-by-character differences
            normalized_correct = normalize_text(correct_answer)
            normalized_option = normalize_text(value)
            
            # Basic difference reporting
            if len(normalized_correct) != len(normalized_option):
                length_diff = f"Length mismatch: correct={len(correct_answer)}, option={len(value)}"
            else:
                length_diff = "Same length"
                
            # Show space differences more clearly for logging
            correct_vis = correct_answer.replace(" ", "␣")
            option_vis = value.replace(" ", "␣")
            
            comparison_info[key] = {
                "option_text": value,
                "exact_match": False,
                "differences": f"{length_diff}; Correct='{correct_vis}', Option='{option_vis}'"
            }
    
    return comparison_info

def validate_correct_answer(mcq):
    """
    Validate if the correct answer text exactly matches one of the options.
    If not, determine the correct answer using the API.
    """
    # Get the options and correct option
    options = {
        "1": mcq.option_1,
        "2": mcq.option_2,
        "3": mcq.option_3,
        "4": mcq.option_4
    }
    current_correct = mcq.correct_option
    
    # Filter out None or empty options
    options = {k: v for k, v in options.items() if v and v.strip()}
    
    # Check if the correct option matches any option EXACTLY (character by character)
    exact_match = False
    match_details = ""
    for key, value in options.items():
        if current_correct == value:  # Using exact comparison, no normalization
            exact_match = True
            match_details = f"Exact match with option {key}"
            break
    
    # If there's no exact match, log the comparison details
    if not exact_match and current_correct:
        comparison_info = identify_closest_option(current_correct, options)
        match_details = f"No exact match. Comparison: {comparison_info}"
        logger.debug(f"MCQ {mcq.uid}: {match_details}")
    
    # If there's an exact match, no need to update
    if exact_match:
        return None, f"No change needed - {match_details}"
    
    # Format options for prompt
    options_text = "\n".join([f"{num}. {option}" for num, option in options.items()])
    
    # Construct the prompt
    prompt = f"""
I need to determine the correct answer for the following medical MCQ.
The current marked correct answer might not match exactly with any of the options.

Question: {mcq.text}

Options:
{options_text}

Current marked correct answer: {current_correct if current_correct else 'Not specified'}

IMPORTANT INSTRUCTIONS:
1. Analyze the question and determine which of the provided options (1, 2, 3, or 4) is most likely the correct answer.
2. Return ONLY the option number AND the EXACT text of that option as it appears in the options list.
3. Do not add any explanations or reasoning - just provide the option number and exact text.
4. Format your response exactly like this: "Option X: [exact option text as provided]"
5. Do NOT modify or paraphrase the option text in any way.
6. The returned option text must match exactly (100% character for character) with the original option.
7. Be careful with spaces, hyphens, capitalization, and punctuation - they must be identical.
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical education expert specializing in determining the correct answers for medical board exam questions. Your task is to analyze the question and options, then select the most likely correct answer from the existing options. You must provide the chosen option EXACTLY as it appears in the original text, with no modifications whatsoever - even minor differences in spacing or punctuation are not acceptable.",
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-4o",
            temperature=0.2,  # Low temperature for more deterministic results
            max_tokens=200,   # We only need a short response
            top_p=1
        )
        
        # Get the API response
        api_response = response.choices[0].message.content.strip()
        
        # Extract the option number and text using regex
        option_match = re.search(r'Option (\d+): (.*)', api_response, re.DOTALL)
        
        if option_match:
            option_number = option_match.group(1)
            option_text = option_match.group(2)  # Don't strip here! Preserve exact spaces
            
            # Get the original option text
            original_option = options.get(option_number)
            
            # Check if the API returned text matches EXACTLY with the original option
            if original_option == option_text:
                # The API correctly returned the exact option text
                # Return the new correct answer and log message
                return original_option, f"Updated from '{current_correct}' to 'Option {option_number}: {original_option}'"
            else:
                # The API didn't return the exact option text, so use the original option text instead
                logger.warning(f"API returned slightly modified option: '{option_text}' vs original: '{original_option}'")
                if option_number in options:
                    return options[option_number], f"Updated from '{current_correct}' to exact option {option_number}: '{options[option_number]}'"
                else:
                    return None, f"API returned invalid option number: {option_number}. No change made."
        else:
            # If we can't parse the API response, don't make changes
            return None, f"Could not parse API response: '{api_response}'. No change made."
            
    except Exception as e:
        logger.error(f"Error calling API: {str(e)}")
        return None, f"API error: {str(e)}. No change made."

def write_log_file(log_entries, subject_name):
    """Write the log entries to a log file."""
    log_file = f"mcq_correction_log_{subject_name.replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    with open(log_file, 'w', encoding='utf-8') as file:
        file.write(f"MCQ Correct Answer Validation Log - {subject_name}\n")
        file.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write("=" * 80 + "\n\n")
        
        file.write(f"Total MCQs Processed: {len(log_entries)}\n")
        updated_count = sum(1 for entry in log_entries if entry['updated'])
        file.write(f"MCQs Updated: {updated_count}\n")
        file.write(f"MCQs Unchanged: {len(log_entries) - updated_count}\n\n")
        
        file.write("DETAILED LOG:\n")
        file.write("-" * 80 + "\n\n")
        
        for entry in log_entries:
            file.write(f"ID: {entry['id']}\n")
            file.write(f"Topic: {entry['topic']}\n")
            file.write(f"Question: {entry['question'][:150]}...\n" if len(entry['question']) > 150 else f"Question: {entry['question']}\n")
            file.write(f"Options:\n")
            file.write(f"1. {entry['option_1']}\n" if entry['option_1'] else "1. [Empty]\n")
            file.write(f"2. {entry['option_2']}\n" if entry['option_2'] else "2. [Empty]\n")
            file.write(f"3. {entry['option_3']}\n" if entry['option_3'] else "3. [Empty]\n")
            file.write(f"4. {entry['option_4']}\n" if entry['option_4'] else "4. [Empty]\n")
            
            # Visualize the original correct option with spaces made visible
            if entry['original']:
                original_vis = entry['original'].replace(" ", "␣")
                file.write(f"Original Correct Option: {entry['original']} (visual: {original_vis})\n")
            else:
                file.write(f"Original Correct Option: None\n")
                
            # Visualize the updated correct option with spaces made visible
            if entry['updated']:
                updated_vis = entry['updated'].replace(" ", "␣")
                file.write(f"Updated Correct Option: {entry['updated']} (visual: {updated_vis})\n")
            else:
                file.write(f"Updated Correct Option: No change\n")
                
            file.write(f"Status: {entry['status']}\n")
            file.write("-" * 50 + "\n\n")
            
    logger.info(f"Log file written to {log_file}")
    return log_file

def validate_mcqs_for_subject(subject_name, batch_size=100, dry_run=False):
    """
    Validate and update MCQs for a specific subject.
    
    Args:
        subject_name: Name of the subject to process
        batch_size: Number of MCQs to process in each batch
        dry_run: If True, don't actually update the database
    
    Returns:
        Tuple of (updated_count, total_count, log_file_path)
    """
    try:
        # Get the subject
        subject = Subject.objects.get(name=subject_name)
        logger.info(f"Found subject: {subject}")
        
        # Get all MCQs for this subject via the related chain
        mcqs = MCQ.objects.filter(topic__chapter__unit__subject=subject)
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
                # Skip if any option is missing
                if not mcq.option_1 or not mcq.option_2 or not mcq.option_3 or not mcq.option_4:
                    log_entry = {
                        'id': mcq.uid,
                        'topic': str(mcq.topic) if mcq.topic else "No topic",
                        'question': mcq.text,
                        'option_1': mcq.option_1,
                        'option_2': mcq.option_2,
                        'option_3': mcq.option_3,
                        'option_4': mcq.option_4,
                        'original': mcq.correct_option,
                        'updated': None,
                        'status': "Skipped - One or more options missing"
                    }
                    log_entries.append(log_entry)
                    logger.warning(f"Skipping MCQ {mcq.uid} - missing options")
                    continue
                
                # Store original correct option for reference
                original_correct = mcq.correct_option
                
                # Validate and potentially update correct answer
                updated_answer, status = validate_correct_answer(mcq)
                
                # Create log entry
                log_entry = {
                    'id': mcq.uid,
                    'topic': str(mcq.topic) if mcq.topic else "No topic",
                    'question': mcq.text,
                    'option_1': mcq.option_1,
                    'option_2': mcq.option_2,
                    'option_3': mcq.option_3,
                    'option_4': mcq.option_4,
                    'original': original_correct,
                    'updated': updated_answer,
                    'status': status
                }
                log_entries.append(log_entry)
                
                # Update the correct option if needed
                if updated_answer and not dry_run:
                    mcq.correct_option = updated_answer
                    mcq.save()
                    updated_count += 1
                    logger.info(f"Updated MCQ {mcq.uid}: {status}")
                else:
                    logger.info(f"MCQ {mcq.uid}: {status}")
        
        # Write log file
        log_file = write_log_file(log_entries, subject_name)
        
        logger.info(f"Process complete! {updated_count} answers updated out of {total_count} questions.")
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
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate and update correct answers for MCQs in a specific subject")
    parser.add_argument("subject", type=str, help="Name of the subject to process")
    parser.add_argument("--batch-size", type=int, default=100, help="Number of MCQs to process in each batch")
    parser.add_argument("--dry-run", action="store_true", help="Run without making actual changes to the database")
    
    args = parser.parse_args()
    
    logger.info(f"Starting MCQ validation for subject: {args.subject}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run: {args.dry_run}")
    
    updated_count, total_count, log_file = validate_mcqs_for_subject(
        args.subject,
        batch_size=args.batch_size,
        dry_run=args.dry_run
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