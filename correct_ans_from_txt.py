import os
import re
from openai import OpenAI
import datetime

# Setup OpenAI client
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key="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",
)

def parse_mcq_file(file_path, limit=None):
    """Parse the MCQ text file into a list of dictionaries with question details.
    Limit to specified number of questions if provided."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Split by delimiter
    questions_raw = content.split('--------------------------------------------------')
    questions = []
    
    # Process only up to the limit if specified
    for q_raw in questions_raw:
        if not q_raw.strip():
            continue
            
        question_data = {}
        
        # Extract UID
        uid_match = re.search(r'UID: ([a-f0-9-]+)', q_raw)
        if uid_match:
            question_data['uid'] = uid_match.group(1)
        
        # Extract question text and options
        question_match = re.search(r'Question: (.*?)(?=\d+\. |\nCorrect Option:)', q_raw, re.DOTALL)
        if question_match:
            question_data['question'] = question_match.group(1).strip()
        
        # Extract options
        options = re.findall(r'(\d+)\. (.*?)(?=\d+\. |\nCorrect Option:|$)', q_raw, re.DOTALL)
        question_data['options'] = {option[0]: option[1].strip() for option in options}
        
        # Extract correct option
        correct_match = re.search(r'Correct Option: (.*?)(?=\nExplanation:|$)', q_raw)
        if correct_match:
            question_data['correct_option'] = correct_match.group(1).strip()
        
        # Extract existing explanation
        explanation_match = re.search(r'Explanation: (.*?)(?=\[|$)', q_raw, re.DOTALL)
        if explanation_match:
            question_data['explanation'] = explanation_match.group(1).strip()
        
        # Extract source if available
        source_match = re.search(r'\[(.*?)\]', q_raw)
        if source_match:
            question_data['source'] = source_match.group(1).strip()
        
        questions.append(question_data)
        
        # Break once we have reached our limit if specified
        if limit and len(questions) >= limit:
            break
    
    return questions

def validate_correct_answer(question_data):
    """Validate if the correct answer text exactly matches one of the options.
    If not, determine the correct answer using the API."""
    
    # First check if the current correct option text matches any of the options exactly
    current_correct = question_data['correct_option']
    options_values = list(question_data['options'].values())
    options_keys = list(question_data['options'].keys())
    
    # Check if the correct option matches any option exactly
    exact_match = False
    for key, value in question_data['options'].items():
        if current_correct.strip() == value.strip():
            exact_match = True
            break
    
    # If there's an exact match, no need to update
    if exact_match:
        return None, "No change needed - correct answer matches an option exactly"
    
    # Format options for prompt
    options_text = "\n".join([f"{num}. {option}" for num, option in question_data['options'].items()])
    
    # Construct the prompt
    prompt = f"""
I need to determine the correct answer for the following medical MCQ.
The current marked correct answer might not match exactly with any of the options.

Question: {question_data['question']}

Options:
{options_text}

Current marked correct answer: {current_correct}

IMPORTANT INSTRUCTIONS:
1. Analyze the question and determine which of the provided options (1, 2, 3, or 4) is most likely the correct answer.
2. Return ONLY the option number AND the EXACT text of that option as it appears in the options list.
3. Do not add any explanations or reasoning - just provide the option number and exact text.
4. Format your response exactly like this: "Option X: [exact option text as provided]"
5. Do NOT modify or paraphrase the option text in any way.
"""

    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a medical education expert specializing in determining the correct answers for medical board exam questions. Your task is to analyze the question and options, then select the most likely correct answer from the existing options.",
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
        option_text = option_match.group(2).strip()
        
        # Verify that the selected option text exactly matches one of our options
        for key, value in question_data['options'].items():
            if option_text.strip() == value.strip() and key == option_number:
                # Return the new correct answer and log message
                return option_text, f"Updated from '{current_correct}' to 'Option {option_number}: {option_text}'"
        
        # If we get here, the API returned an option that doesn't match our options exactly
        return None, f"API returned non-matching option: '{option_text}'. No change made."
    else:
        # If we can't parse the API response, don't make changes
        return None, f"Could not parse API response: '{api_response}'. No change made."

def write_updated_mcq_file(questions, output_file):
    """Write the updated MCQs with validated correct answers to a new file."""
    with open(output_file, 'w', encoding='utf-8') as file:
        for i, q in enumerate(questions):
            file.write(f"UID: {q['uid']}\n")
            file.write(f"Question: {q['question']}\n")
            
            # Write options
            for num, option in q['options'].items():
                file.write(f"{num}. {option}\n")
            
            # Write the correct option (updated if necessary)
            file.write(f"Correct Option: {q['correct_option']}\n")
            
            # Write explanation
            if 'explanation' in q:
                file.write(f"Explanation: {q['explanation']}")
            
            # Add source if available
            if 'source' in q:
                file.write(f"[{q['source']}]")
            
            # Add delimiter except for the last question
            if i < len(questions) - 1:
                file.write("\n--------------------------------------------------\n")

def write_log_file(log_entries, log_file):
    """Write the log entries to a log file."""
    with open(log_file, 'w', encoding='utf-8') as file:
        file.write(f"MCQ Correct Answer Validation Log - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write("=" * 80 + "\n\n")
        
        for entry in log_entries:
            file.write(f"UID: {entry['uid']}\n")
            file.write(f"Question: {entry['question'][:100]}...\n")  # Show first 100 chars of question
            file.write(f"Original Correct Option: {entry['original']}\n")
            file.write(f"Updated Correct Option: {entry['updated'] if entry['updated'] else 'No change'}\n")
            file.write(f"Status: {entry['status']}\n")
            file.write("-" * 50 + "\n\n")

def main():
    input_file = "Obstetrics_MCQs.txt"  # Change this to your input file path
    output_file = "mcq_corrected_answers.txt"
    log_file = "mcq_correction_log.txt"
    max_questions = None  # Process all questions by default, set a number to limit
    
    print("Parsing MCQ file...")
    questions = parse_mcq_file(input_file, limit=max_questions)
    
    print(f"Found {len(questions)} questions. Validating correct answers...")
    
    log_entries = []
    updated_count = 0
    
    for i, question in enumerate(questions):
        print(f"Processing question {i+1}/{len(questions)}...")
        
        # Store original correct option for reference
        original_correct = question['correct_option']
        
        # Validate and potentially update correct answer
        updated_answer, status = validate_correct_answer(question)
        
        # Create log entry
        log_entry = {
            'uid': question['uid'],
            'question': question['question'],
            'original': original_correct,
            'updated': updated_answer,
            'status': status
        }
        log_entries.append(log_entry)
        
        # Update the correct option if needed
        if updated_answer:
            question['correct_option'] = updated_answer
            updated_count += 1
            print(f"  → Updated correct answer: {status}")
        else:
            print(f"  → {status}")
    
    print("Writing updated MCQs to file...")
    write_updated_mcq_file(questions, output_file)
    
    print("Writing log file...")
    write_log_file(log_entries, log_file)
    
    print(f"Process complete! {updated_count} answers updated out of {len(questions)} questions.")
    print(f"Updated MCQs saved to: {output_file}")
    print(f"Change log saved to: {log_file}")

if __name__ == "__main__":
    main()