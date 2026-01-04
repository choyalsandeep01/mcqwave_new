import os
import re
from openai import OpenAI

# Setup OpenAI client
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key="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",
)

def parse_mcq_file(file_path, limit=10):
    """Parse the MCQ text file into a list of dictionaries with question details.
    Limit to specified number of questions."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Split by delimiter
    questions_raw = content.split('--------------------------------------------------')
    questions = []
    
    # Process only up to the limit
    for q_raw in questions_raw[:limit+1]:  # +1 because there might be empty strings
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
        
        # Break once we have reached our limit
        if len(questions) >= limit:
            break
    
    return questions

def get_detailed_explanation(question_data):
    """Get a detailed explanation for the question using the API."""
    
    # Format options for prompt
    options_text = "\n".join([f"{num}. {option}" for num, option in question_data['options'].items()])
    
    # Construct the prompt
    prompt = f"""
I need a detailed and organized explanation for the following medical MCQ:

Question: {question_data['question']}
Options:
{options_text}
Correct Answer: {question_data['correct_option']}
Current Brief Explanation: {question_data.get('explanation', 'None provided')}
Source: {question_data.get('source', 'Not specified')}

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
    
    return clean_explanation

def write_updated_mcq_file(questions, output_file):
    """Write the updated MCQs with detailed explanations to a new file."""
    with open(output_file, 'w', encoding='utf-8') as file:
        for i, q in enumerate(questions):
            file.write(f"UID: {q['uid']}\n")
            file.write(f"Question: {q['question']}\n")
            
            # Write options
            for num, option in q['options'].items():
                file.write(f"{num}. {option}\n")
            
            file.write(f"Correct Option: {q['correct_option']}\n")
            file.write(f"Explanation: {q['detailed_explanation']}")
            
            if 'source' in q:
                file.write(f"[{q['source']}]")
            
            # Add delimiter except for the last question
            if i < len(questions) - 1:
                file.write("\n--------------------------------------------------\n")

def main():
    input_file = "Obstetrics_MCQs.txt"  # Change this to your input file path
    output_file = "mcq_organized_explanations.txt"
    max_questions = 5  # Limit to 10 MCQs
    
    print("Parsing MCQ file...")
    questions = parse_mcq_file(input_file, limit=max_questions)
    
    print(f"Found {len(questions)} questions. Generating organized explanations for {min(max_questions, len(questions))} questions...")
    for i, question in enumerate(questions):
        print(f"Processing question {i+1}/{len(questions)}...")
        question['detailed_explanation'] = get_detailed_explanation(question)
    
    print("Writing updated explanations to file...")
    write_updated_mcq_file(questions, output_file)
    
    print(f"Process complete! Organized explanations saved to {output_file}")

if __name__ == "__main__":
    main()