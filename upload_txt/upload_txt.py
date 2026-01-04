import os
import django
import traceback
import logging
from datetime import datetime

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

# Import your models
from mcqs.models import Subject, Unit, Chapter, Topic, difficulties, mcq_types, MCQ

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='mcq_txt_upload_log.txt')
logger = logging.getLogger(__name__)

def normalize_text(text):
    """
    Normalize text to match database entries
    Converts to title case, ensuring first letter is capital
    """
    return text.strip().title()

def validate_difficulty(difficulty_name):
    """
    Validate if difficulty exists in the database
    """
    try:
        normalized_difficulty = normalize_text(difficulty_name)
        difficulty = difficulties.objects.filter(name=normalized_difficulty).first()
        
        if not difficulty:
            logger.error(f"Difficulty '{difficulty_name}' does not exist in the database.")
            return None
        
        return difficulty
    except Exception as e:
        logger.error(f"Error validating difficulty {difficulty_name}: {e}")
        return None

def validate_mcq_type(mcq_type):
    """
    Validate if MCQ type exists in the database
    """
    try:
        normalized_type = normalize_text(mcq_type)
        mcq_type_obj = mcq_types.objects.filter(types=normalized_type).first()
        
        if not mcq_type_obj:
            logger.error(f"MCQ Type '{mcq_type}' does not exist in the database.")
            return None
        
        return mcq_type_obj
    except Exception as e:
        logger.error(f"Error validating MCQ type {mcq_type}: {e}")
        return None

def parse_mcq(mcq_lines):
    """
    Parse MCQ entry from text lines
    """
    # Join all lines, removing extra whitespaces
    full_text = ' '.join([line.strip() for line in mcq_lines])
    
    logger.debug(f"Full MCQ text: {full_text}")
    
    try:
        # Split by '|'
        parts = [p.strip() for p in full_text.split('|')]
        
        # Validate minimum number of parts
        if len(parts) < 7:
            logger.error(f"Insufficient parts in MCQ: {full_text}")
            return None
        
        # Extract question (first part)
        question = parts[0]
        
        # Handling options and correct answer
        options = parts[1:5]
        correct_answer = parts[5]
        explanation = parts[6]
        
        # Default difficulty and type if not specified
        difficulty = parts[7] if len(parts) > 7 else 'Easy'
        mcq_type = parts[8] if len(parts) > 8 else 'General'
        
        # Construct full parts list
        full_parts = [
            question,      # 0: Question
            options[0],    # 1: Option 1
            options[1],    # 2: Option 2
            options[2],    # 3: Option 3
            options[3],    # 4: Option 4
            correct_answer,# 5: Correct Option
            explanation,   # 6: Explanation
            difficulty,    # 7: Difficulty
            mcq_type      # 8: MCQ Type
        ]
        
        logger.debug(f"Parsed MCQ parts: {full_parts}")
        return full_parts
    
    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
        logger.error(f"Full text: {full_text}")
        return None

def process_txt_file(file_path):
    """
    Process TXT file and upload to database
    Creates two files:
    1. Updated original file with only non-uploaded content
    2. New file with successfully uploaded content
    """
    try:
        # Get subject name from filename
        subject_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Create or get subject
        subject, _ = Subject.objects.get_or_create(name=subject_name)
        
        current_unit = None
        current_chapter = None
        current_topic = None
        
        # Track successfully uploaded MCQs and their context
        uploaded_content = []
        uploaded_lines = set()
        current_context = {
            'unit': None,
            'chapter': None,
            'topic': None
        }
        
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        # Process lines
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Context management (Unit, Chapter, Topic)
            if line.lower().startswith('unit-'):
                unit_name = line.split('-', 1)[1].strip()
                current_unit, _ = Unit.objects.get_or_create(
                    subject=subject, 
                    name=unit_name
                )
                current_chapter = None
                current_topic = None
                current_context['unit'] = line
                current_context['chapter'] = None
                current_context['topic'] = None
                i += 1
                continue
            
            elif line.lower().startswith('chapter-'):
                chapter_name = line.split('-', 1)[1].strip()
                
                if not current_unit:
                    logger.warning(f"Chapter {chapter_name} found without a preceding unit. Skipping.")
                    i += 1
                    continue
                
                current_chapter, _ = Chapter.objects.get_or_create(
                    unit=current_unit, 
                    name=chapter_name
                )
                
                current_topic, _ = Topic.objects.get_or_create(
                    chapter=current_chapter, 
                    name=chapter_name
                )
                current_context['chapter'] = line
                current_context['topic'] = None
                i += 1
                continue
            
            elif line.lower().startswith('topic-'):
                topic_name = line.split('-', 1)[1].strip()
                
                if not current_chapter:
                    logger.warning(f"Topic {topic_name} found without a preceding chapter. Skipping.")
                    i += 1
                    continue
                
                current_topic, _ = Topic.objects.get_or_create(
                    chapter=current_chapter, 
                    name=topic_name
                )
                current_context['topic'] = line
                i += 1
                continue
            
            # MCQ Detection
            if '|' in line:
                # Ensure chapter exists
                if not current_chapter:
                    logger.warning("MCQ found without a chapter. Skipping.")
                    i += 1
                    continue
                
                # If no topic was explicitly defined, use chapter name as topic
                if not current_topic:
                    current_topic, _ = Topic.objects.get_or_create(
                        chapter=current_chapter, 
                        name=current_chapter.name
                    )
                
                # Collect MCQ lines
                mcq_lines = [line]
                current_line = i
                
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if '|' in next_line or len(mcq_lines) >= 6:
                        break
                    if next_line:
                        mcq_lines.append(next_line)
                        current_line = j
                
                # Parse the MCQ
                parts = parse_mcq(mcq_lines)
                
                # Validate MCQ parts
                if not parts or len(parts) < 8:
                    logger.error(f"Incomplete MCQ data. Parts found: {parts}")
                    i = current_line + 1
                    continue
                
                # Validate difficulty
                difficulty = validate_difficulty(parts[7])
                if not difficulty:
                    logger.error(f"Skipping MCQ due to invalid difficulty: {parts[7]}")
                    i = current_line + 1
                    continue
                
                # Validate MCQ type
                mcq_type = validate_mcq_type(parts[8] if len(parts) > 8 else 'General')
                if not mcq_type:
                    logger.error(f"Skipping MCQ due to invalid type: {parts[8] if len(parts) > 8 else 'General'}")
                    i = current_line + 1
                    continue
                
                # Prepare MCQ data
                try:
                    mcq_data = {
                        'text': parts[0],
                        'option_1': parts[1],
                        'option_2': parts[2],
                        'option_3': parts[3],
                        'option_4': parts[4],
                        'correct_option': parts[5],
                        'explanation': parts[6],
                        'topic': current_topic,
                        'difficulty': difficulty,
                        'types': mcq_type
                    }
                    
                    # Create MCQ
                    MCQ.objects.create(**mcq_data)
                    logger.info(f"Successfully uploaded MCQ: {mcq_data['text'][:50]}...")
                    
                    # Store the context and content for successful uploads
                    mcq_content = {
                        'context': current_context.copy(),
                        'lines': mcq_lines
                    }
                    uploaded_content.append(mcq_content)
                    uploaded_lines.update(range(i, current_line + 1))
                    
                except Exception as mcq_error:
                    logger.error(f"Error creating MCQ: {mcq_error}")
                    logger.error(traceback.format_exc())
                
                i = current_line + 1
                continue
            
            i += 1
        
        # Create file with remaining content
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        remaining_file_path = os.path.join(
            os.path.dirname(file_path),
            f'remaining_{os.path.basename(file_path)}_{timestamp}.txt'
        )
        
        with open(remaining_file_path, 'w', encoding='utf-8') as remaining_file:
            for i, line in enumerate(lines):
                if i not in uploaded_lines:
                    remaining_file.write(line)
        
        # Create file with uploaded content
        uploaded_file_path = os.path.join(
            os.path.dirname(file_path),
            f'uploaded_{os.path.basename(file_path)}_{timestamp}.txt'
        )
        
        with open(uploaded_file_path, 'w', encoding='utf-8') as uploaded_file:
            uploaded_file.write(f'Uploaded MCQs - {subject_name}\n\n')
            
            current_unit = None
            current_chapter = None
            current_topic = None
            
            for content in uploaded_content:
                # Add context headers if they've changed
                if content['context']['unit'] != current_unit:
                    uploaded_file.write(f"{content['context']['unit']}\n")
                    current_unit = content['context']['unit']
                
                if content['context']['chapter'] != current_chapter:
                    uploaded_file.write(f"{content['context']['chapter']}\n")
                    current_chapter = content['context']['chapter']
                
                if content['context']['topic'] != current_topic:
                    uploaded_file.write(f"{content['context']['topic']}\n")
                    current_topic = content['context']['topic']
                
                # Add MCQ content
                for line in content['lines']:
                    uploaded_file.write(f"{line}\n")
                
                # Add spacing between MCQs
                uploaded_file.write('\n')
        
        logger.info(f"Created uploaded content file: {uploaded_file_path}")
        logger.info(f"Completed processing file: {file_path}")
    
    except Exception as file_error:
        logger.error(f"Error processing file {file_path}: {file_error}")
        logger.error(traceback.format_exc())

def main():
    """
    Main function to process MCQ files
    """
    mcq_directory = os.getcwd()
    # Directory containing MCQ TXT files
    
    # Process all TXT files in the directory
    for filename in os.listdir(mcq_directory):
        if filename.endswith('.txt'):
            file_path = os.path.join(mcq_directory, filename)
            process_txt_file(file_path)

if __name__ == '__main__':
    main()
    print("MCQ upload process completed. Check mcq_txt_upload_log.txt for details.")