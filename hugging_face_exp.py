import os
import re
import json
import time
import requests
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables from .env file if you have one
load_dotenv()

# HuggingFace API configurations
API_URL = "https://api-inference.huggingface.co/models/epfl-llm/meditron-70b"
API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")  # Set your API token in environment variables

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

def parse_mcq_file(file_path):
    """Parse the MCQ file and extract questions, options, correct answers, and explanations."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Split the content by the delimiter
    questions_data = content.split("--------------------------------------------------")
    mcq_list = []
    
    for question_block in questions_data:
        if not question_block.strip():
            continue
        
        # Extract UID
        uid_match = re.search(r"UID: ([a-f0-9-]+)", question_block)
        uid = uid_match.group(1) if uid_match else None
        
        # Extract question
        question_match = re.search(r"Question: (.*?)(?=\d+\.|\n\d+\.)", question_block, re.DOTALL)
        question = question_match.group(1).strip() if question_match else None
        
        # Extract options
        options = []
        options_matches = re.findall(r"(\d+)\. (.*?)(?=\d+\.|Correct Option:|$)", question_block, re.DOTALL)
        for num, option in options_matches:
            options.append((num, option.strip()))
        
        # Extract correct option
        correct_match = re.search(r"Correct Option: (.*?)(?=\n|$)", question_block)
        correct_option = correct_match.group(1).strip() if correct_match else None
        
        # Extract current explanation
        explanation_match = re.search(r"Explanation: (.*?)(?=\n--|$)", question_block, re.DOTALL)
        explanation = explanation_match.group(1).strip() if explanation_match else None
        
        # Create a structured dictionary
        mcq_data = {
            "uid": uid,
            "question": question,
            "options": options,
            "correct_option": correct_option,
            "current_explanation": explanation
        }
        
        mcq_list.append(mcq_data)
    
    return mcq_list

def generate_enhanced_explanation(mcq_data):
    """Generate an enhanced explanation using Meditron 70B."""
    # Construct the prompt for Meditron
    prompt = f"""
You are a medical education expert. Please analyze the following medical MCQ and provide a detailed explanation:

Question: {mcq_data['question']}

Options:
{chr(10).join([f"{num}. {option}" for num, option in mcq_data['options']])}

Correct Answer: {mcq_data['correct_option']}

Current Explanation: {mcq_data['current_explanation']}

Please provide a comprehensive explanation that includes:
1. Detailed reasoning why the correct answer is right
2. Explanation of why each incorrect option is wrong
3. Mnemonic device, trick, or key concept to help remember this information
4. Any clinical relevance or practical application
"""

    # Call the Meditron API
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 500,
            "temperature": 0.7,
            "top_p": 0.95,
            "return_full_text": False
        }
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        
        # Check if the model is loading
        if response.status_code == 503:
            estimated_time = json.loads(response.text).get("estimated_time", 20)
            print(f"Model is loading. Waiting for {estimated_time} seconds...")
            time.sleep(estimated_time)
            return generate_enhanced_explanation(mcq_data)  # Retry
            
        # Handle other potential errors
        response.raise_for_status()
        
        result = response.json()
        if isinstance(result, list) and len(result) > 0:
            enhanced_explanation = result[0].get("generated_text", "")
        else:
            enhanced_explanation = result.get("generated_text", "")
            
        return enhanced_explanation.strip()
        
    except requests.exceptions.RequestException as e:
        print(f"Error calling API: {e}")
        return f"Failed to generate explanation: {str(e)}"
    except json.JSONDecodeError:
        print(f"Invalid JSON response: {response.text}")
        return "Failed to parse API response"

def save_updated_mcqs(mcq_list, output_file):
    """Save the updated MCQs with enhanced explanations to a new file."""
    with open(output_file, 'w', encoding='utf-8') as file:
        for i, mcq in enumerate(mcq_list):
            file.write(f"UID: {mcq['uid']}\n")
            file.write(f"Question: {mcq['question']}\n")
            
            for num, option in mcq['options']:
                file.write(f"{num}. {option}\n")
            
            file.write(f"Correct Option: {mcq['correct_option']}\n")
            file.write(f"Explanation: {mcq['enhanced_explanation']}\n")
            
            # Add delimiter except for the last MCQ
            if i < len(mcq_list) - 1:
                file.write("\n--------------------------------------------------\n\n")

def main():
    # File paths
    input_file = "Obstetrics_MCQs.txt"  # Change to your input file path
    output_file = "enhanced_medical_mcqs.txt"
    
    # Parse the input file
    print("Parsing MCQ file...")
    mcq_list = parse_mcq_file(input_file)
    
    # For testing, limit to the first 10 MCQs
    mcq_list = mcq_list[:10]
    
    print(f"Found {len(mcq_list)} MCQs. Enhancing explanations for the first 10...")
    
    # Process each MCQ and generate enhanced explanations
    for mcq in tqdm(mcq_list):
        print(f"\nProcessing MCQ: {mcq['question'][:50]}...")
        enhanced_explanation = generate_enhanced_explanation(mcq)
        mcq['enhanced_explanation'] = enhanced_explanation
        
        # Print a sample of the enhanced explanation
        print(f"Original explanation: {mcq['current_explanation'][:100]}...")
        print(f"Enhanced explanation (preview): {enhanced_explanation[:100]}...")
        print("-" * 40)
        
        # Add a short delay to avoid rate limits
        time.sleep(2)
    
    # Save the updated MCQs
    save_updated_mcqs(mcq_list, output_file)
    print(f"\nEnhanced MCQs saved to {output_file}")

if __name__ == "__main__":
    # Check if API token is set
    if not API_TOKEN:
        print("Error: Hugging Face API token not found. Please set the HUGGINGFACE_API_TOKEN environment variable.")
        print("You can get a token from https://huggingface.co/settings/tokens")
        exit(1)
    
    main()