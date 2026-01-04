import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from mcqs.models import Subject, Unit, Chapter, Topic

def generate_subject_index(subject_name):
    try:
        # Get the subject by name (case-insensitive)
        subject = Subject.objects.filter(name__iexact=subject_name).first()
        
        if not subject:
            return f"Subject '{subject_name}' not found! Use -l to see available subjects."
        
        # Create filename based on subject name
        filename = f"{subject.name}_index.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            # Get all units for this subject
            units = Unit.objects.filter(subject=subject).order_by('order')
            
            for unit in units:
                # Get all chapters for this unit
                chapters = Chapter.objects.filter(unit=unit).order_by('order')
                
                for chapter in chapters:
                    # Get all topics for this chapter
                    topics = Topic.objects.filter(chapter=chapter).order_by('order')
                    
                    for topic in topics:
                        # Write the hierarchical information with proper spacing
                        f.write(f"Unit-{unit.name}\n")
                        f.write(f"Chapter-{chapter.name}\n")
                        f.write(f"Topic-{topic.name}\n")
                        
                        # Add two blank lines between entries
                        f.write("\n\n")
            
        return f"Index file '{filename}' has been generated successfully!"
    
    except Exception as e:
        return f"An error occurred: {str(e)}"

def list_subjects():
    """List all available subjects"""
    subjects = Subject.objects.all().order_by('order')
    print("\nAvailable Subjects:")
    print("------------------")
    for subject in subjects:
        print(f"- {subject.name}")
    print()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate index file for a specific subject')
    parser.add_argument('-l', '--list', action='store_true', help='List all available subjects')
    parser.add_argument('-s', '--subject', type=str, help='Subject name to generate index for')
    
    args = parser.parse_args()
    
    if args.list:
        list_subjects()
    elif args.subject:
        result = generate_subject_index(args.subject)
        print(result)
    else:
        print("Please either use -l to list subjects or -s \"subject name\" to generate an index.")
        print("Example usage:")
        print("  python index_generator.py -l                    # List all subjects")
        print('  python index_generator.py -s "Mathematics"      # Generate index for Mathematics')