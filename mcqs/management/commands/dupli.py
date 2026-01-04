from django.core.management.base import BaseCommand
from django.db.models import Count
from mcqs.models import MCQ  # Replace 'your_app' with your actual app name

class Command(BaseCommand):
    help = 'Find duplicate MCQ texts'

    def handle(self, *args, **options):
        # Find MCQs with duplicate text, grouped by text
        duplicates = MCQ.objects.values('text').annotate(
            count=Count('uid')
        ).filter(count__gt=1).order_by('-count')
        
        self.stdout.write(self.style.SUCCESS("=== Duplicate MCQ Texts ==="))
        if not duplicates:
            self.stdout.write(self.style.SUCCESS("No duplicate MCQ texts found."))
            return
        
        for dup in duplicates:
            # Find all MCQs with this text
            mcqs = MCQ.objects.filter(text=dup['text'])
            
            self.stdout.write(f"\nDuplicate Text: {dup['text']}")
            self.stdout.write(f"Number of Duplicates: {dup['count']}")
            self.stdout.write("Duplicate MCQ Details:")
            for mcq in mcqs:
                self.stdout.write(f"- ID: {mcq.uid}")
                self.stdout.write(f"  Topic: {mcq.topic}")
                self.stdout.write(f"  Difficulty: {mcq.difficulty}")
                self.stdout.write(f"  Type: {mcq.types}")
                self.stdout.write("  Options:")
                self.stdout.write(f"    1. {mcq.option_1}")
                self.stdout.write(f"    2. {mcq.option_2}")
                self.stdout.write(f"    3. {mcq.option_3}")
                self.stdout.write(f"    4. {mcq.option_4}")
                self.stdout.write(f"  Correct Option: {mcq.correct_option}")
                self.stdout.write(f"  Explanation: {mcq.explanation[:100]}...")  # First 100 chars
                self.stdout.write("---")