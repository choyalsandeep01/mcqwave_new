import os
import django
import logging
from datetime import datetime
from collections import defaultdict

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from mcqs.models import MCQ, Subject, Unit, Chapter, Topic

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s\nDetails: %(details)s\n',
    filename='mcq_validation_log.txt'
)
logger = logging.getLogger(__name__)

class MCQValidator:
    def __init__(self, mcq):
        self.mcq = mcq
        self.errors = []
        
    def get_mcq_identifier(self):
        """Get a string identifier for the MCQ, fallback to text if id is missing"""
        try:
            mcq_id = getattr(self.mcq, 'id', 'Unknown ID')
            question_text = (self.mcq.text[:100] + '...') if self.mcq.text and len(self.mcq.text) > 100 else self.mcq.text
            return f"MCQ(id={mcq_id}, text='{question_text}')"
        except AttributeError as e:
            return f"MCQ(text='{getattr(self.mcq, 'text', 'Unknown text')}')"
    
    def validate_question_text(self):
        """Check if question text is empty"""
        try:
            if not self.mcq.text or self.mcq.text.strip() == '' or self.mcq.text.strip() == 'Default question text':
                self.errors.append("Question text is empty or default")
                return False
            return True
        except AttributeError as e:
            self.errors.append(f"Question text validation error: {str(e)}")
            return False
    
    def validate_options(self):
        """Check if any option is empty"""
        try:
            empty_options = []
            
            if not self.mcq.option_1 or self.mcq.option_1.strip() == '':
                empty_options.append("Option 1")
            if not self.mcq.option_2 or self.mcq.option_2.strip() == '':
                empty_options.append("Option 2")
            if not self.mcq.option_3 or self.mcq.option_3.strip() == '':
                empty_options.append("Option 3")
            if not self.mcq.option_4 or self.mcq.option_4.strip() == '':
                empty_options.append("Option 4")
                
            if empty_options:
                self.errors.append(f"Empty options found: {', '.join(empty_options)}")
                return False
            return True
        except AttributeError as e:
            self.errors.append(f"Options validation error: {str(e)}")
            return False
    
    def validate_correct_answer(self):
        """Check if correct answer exists in options"""
        try:
            if not self.mcq.correct_option or self.mcq.correct_option.strip() == '':
                self.errors.append("Correct answer is empty")
                return False
                
            options = [
                self.mcq.option_1,
                self.mcq.option_2,
                self.mcq.option_3,
                self.mcq.option_4
            ]
            
            # Strip whitespace for comparison
            correct_answer = self.mcq.correct_option.strip()
            options = [opt.strip() if opt else '' for opt in options]
            
            if correct_answer not in options:
                self.errors.append("Correct answer does not match any option exactly")
                return False
            return True
        except AttributeError as e:
            self.errors.append(f"Correct answer validation error: {str(e)}")
            return False
    
    def validate_explanation(self):
        """Check if explanation is empty"""
        try:
            if not self.mcq.explanation or self.mcq.explanation.strip() == '':
                self.errors.append("Explanation is empty")
                return False
            return True
        except AttributeError as e:
            self.errors.append(f"Explanation validation error: {str(e)}")
            return False
    
    def validate(self):
        """Run all validations"""
        is_valid = True
        
        if not self.validate_question_text():
            is_valid = False
        if not self.validate_options():
            is_valid = False
        if not self.validate_correct_answer():
            is_valid = False
        if not self.validate_explanation():
            is_valid = False
            
        return is_valid, self.errors

def get_subject_for_mcq(mcq):
    """Get the subject for an MCQ, handling potential null relationships"""
    try:
        if mcq.topic and mcq.topic.chapter and mcq.topic.chapter.unit and mcq.topic.chapter.unit.subject:
            return mcq.topic.chapter.unit.subject
        return None
    except (AttributeError, Exception) as e:
        logger.error(
            "Error retrieving subject for MCQ",
            extra={
                'details': f"MCQ ID: {getattr(mcq, 'id', 'Unknown')}\nError: {str(e)}"
            }
        )
        return None

def validate_all_mcqs():
    """Validate all MCQs in the database with subject-wise error counts"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'mcq_validation_report_{timestamp}.txt'
    
    try:
        all_mcqs = MCQ.objects.all()
        invalid_mcqs = []
        
        # Track subject-wise error counts
        subject_error_counts = defaultdict(int)
        subject_total_counts = defaultdict(int)
        
        # Also track MCQs without subjects
        no_subject_errors = 0
        no_subject_total = 0
        
        print(f"Starting validation of {all_mcqs.count()} MCQs...")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("MCQ Validation Report\n")
            f.write("===================\n\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total MCQs checked: {all_mcqs.count()}\n\n")
            
            for mcq in all_mcqs:
                validator = MCQValidator(mcq)
                try:
                    # Get subject for this MCQ
                    subject = get_subject_for_mcq(mcq)
                    
                    if subject:
                        subject_name = subject.name
                        subject_total_counts[subject_name] += 1
                    else:
                        no_subject_total += 1
                        subject_name = "No Subject"
                    
                    is_valid, errors = validator.validate()
                    
                    if not is_valid:
                        invalid_mcqs.append((mcq, errors))
                        
                        # Track error by subject
                        if subject:
                            subject_error_counts[subject_name] += 1
                        else:
                            no_subject_errors += 1
                        
                        mcq_identifier = validator.get_mcq_identifier()
                        f.write(f"\n{mcq_identifier}\n")
                        f.write(f"Subject: {subject_name}\n")
                        f.write("Errors found:\n")
                        for error in errors:
                            f.write(f"- {error}\n")
                        
                        # Log full MCQ details with proper error handling
                        f.write("\nFull MCQ Details:\n")
                        try:
                            f.write(f"Question: {getattr(mcq, 'text', 'N/A')}\n")
                            f.write(f"Option 1: {getattr(mcq, 'option_1', 'N/A')}\n")
                            f.write(f"Option 2: {getattr(mcq, 'option_2', 'N/A')}\n")
                            f.write(f"Option 3: {getattr(mcq, 'option_3', 'N/A')}\n")
                            f.write(f"Option 4: {getattr(mcq, 'option_4', 'N/A')}\n")
                            f.write(f"Correct Answer: {getattr(mcq, 'correct_option', 'N/A')}\n")
                            f.write(f"Explanation: {getattr(mcq, 'explanation', 'N/A')}\n")
                        except Exception as e:
                            f.write(f"Error retrieving MCQ details: {str(e)}\n")
                        f.write("-" * 80 + "\n")
                
                except Exception as e:
                    logger.error(
                        "Error validating MCQ",
                        extra={
                            'details': f"MCQ: {validator.get_mcq_identifier()}\nError: {str(e)}"
                        }
                    )
            
            # Write overall summary
            f.write("\nSummary:\n")
            f.write(f"Total MCQs with errors: {len(invalid_mcqs)}\n")
            f.write(f"Percentage valid: {((all_mcqs.count() - len(invalid_mcqs)) / all_mcqs.count() * 100):.2f}%\n")
            
            # Write subject-wise summary
            f.write("\nSubject-wise Error Summary:\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'Subject':<40} | {'Total MCQs':<10} | {'Error MCQs':<10} | {'Error %':<10}\n")
            f.write("-" * 80 + "\n")
            
            # Get all subjects to include those with no errors too
            all_subjects = list(Subject.objects.all())
            subject_names = {s.name for s in all_subjects}
            
            # Add subjects that have MCQs but might not be in the all_subjects query
            for subject_name in subject_total_counts.keys():
                subject_names.add(subject_name)
            
            # Sort subjects alphabetically for better readability
            for subject_name in sorted(subject_names):
                total = subject_total_counts.get(subject_name, 0)
                errors = subject_error_counts.get(subject_name, 0)
                if total > 0:
                    error_percent = (errors / total * 100)
                    f.write(f"{subject_name:<40} | {total:<10} | {errors:<10} | {error_percent:.2f}%\n")
            
            # Add the "No Subject" row at the end if there are any
            if no_subject_total > 0:
                error_percent = (no_subject_errors / no_subject_total * 100) if no_subject_total > 0 else 0
                f.write(f"{'No Subject':<40} | {no_subject_total:<10} | {no_subject_errors:<10} | {error_percent:.2f}%\n")
            
            f.write("-" * 80 + "\n")
            
            # Add summary statistics to the log file
            logger.info(
                "Validation complete",
                extra={
                    'details': f"Total MCQs: {all_mcqs.count()}\n"
                              f"Invalid MCQs: {len(invalid_mcqs)}\n"
                              f"Subject-wise Errors: {dict(subject_error_counts)}"
                }
            )
        
        print(f"\nValidation complete. Results saved to {output_file}")
        print(f"Found {len(invalid_mcqs)} MCQs with errors out of {all_mcqs.count()} total MCQs")
        
        # Print subject-wise summary to console
        print("\nSubject-wise Error Summary:")
        print(f"{'Subject':<40} | {'Total MCQs':<10} | {'Error MCQs':<10} | {'Error %':<10}")
        print("-" * 80)
        
        for subject_name in sorted(subject_names):
            total = subject_total_counts.get(subject_name, 0)
            errors = subject_error_counts.get(subject_name, 0)
            if total > 0:
                error_percent = (errors / total * 100)
                print(f"{subject_name:<40} | {total:<10} | {errors:<10} | {error_percent:.2f}%")
        
        if no_subject_total > 0:
            error_percent = (no_subject_errors / no_subject_total * 100) if no_subject_total > 0 else 0
            print(f"{'No Subject':<40} | {no_subject_total:<10} | {no_subject_errors:<10} | {error_percent:.2f}%")
        
        return invalid_mcqs
    
    except Exception as e:
        error_details = f"Error during validation process: {str(e)}"
        logger.error("Validation process failed", extra={'details': error_details})
        print(f"An error occurred. Check mcq_validation_log.txt for details.")
        return []

if __name__ == '__main__':
    try:
        invalid_mcqs = validate_all_mcqs()
        
        if invalid_mcqs:
            print("\nExample of errors found:")
            for mcq, errors in invalid_mcqs[:3]:  # Show first 3 examples
                validator = MCQValidator(mcq)
                subject = get_subject_for_mcq(mcq)
                subject_name = subject.name if subject else "No Subject"
                print(f"\n{validator.get_mcq_identifier()}")
                print(f"Subject: {subject_name}")
                print("Errors:")
                for error in errors:
                    print(f"- {error}")
    except Exception as e:
        logger.error("Main execution failed", extra={'details': str(e)})