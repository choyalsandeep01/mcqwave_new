from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from base.models import BaseModel
import random
from datetime import timedelta
from mcqs.models import MCQ, Subject, Topic, Chapter, Unit, difficulties, mcq_types
from django.utils.html import format_html

MOCK_TEST_CATEGORIES = [
    ('NEET-PG Pattern', 'NEET PG Pattern'),
    ('INI-CET', 'INI-CET'),
    ('FMGE', 'FMGE'),
]

# Mock Test Type Choices
MOCK_TEST_TYPES = [
    ('FULL', 'Full Syllabus'),
    ('SUBJECT', 'Subject Specific'),
]

class MockTestCategory(BaseModel):
    name = models.CharField(max_length=100, choices=MOCK_TEST_CATEGORIES)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.get_name_display()
    
    class Meta:
        verbose_name_plural = "Mock Test Categories"


class MockTest(BaseModel):
    category = models.ForeignKey(MockTestCategory, on_delete=models.CASCADE, related_name='mock_tests')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    test_type = models.CharField(max_length=50, choices=MOCK_TEST_TYPES)
    
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    time_limit_minutes = models.PositiveIntegerField(default=180)
    is_active = models.BooleanField(default=True)
    
    subjects = models.ManyToManyField(Subject, blank=True, related_name='mock_tests')
    
    total_mcqs = models.PositiveIntegerField(default=180)
    percent_pyq = models.PositiveIntegerField(default=0)
    
    percent_easy = models.PositiveIntegerField(default=33)
    percent_medium = models.PositiveIntegerField(default=34)
    percent_hard = models.PositiveIntegerField(default=33)
    
    # Updated: Store as JSON with type names as keys and percentages as values
    # Example: {"Image": 40, "General": 30, "Clinical": 30}
    mcq_types_distribution = models.JSONField(
        default=dict, 
        blank=True, 
        null=True,
        help_text="JSON object with MCQ type names as keys and percentages as values. Example: {'Image': 40, 'General': 30, 'Clinical': 30}"
    )
    
    subject_distribution = models.JSONField(default=dict, blank=True, null=True)
    
    percent_most_correct = models.PositiveIntegerField(default=0)
    percent_most_incorrect = models.PositiveIntegerField(default=0)
    
    total_students = models.PositiveIntegerField(default=0)
    seed = models.PositiveIntegerField(default=0, editable=False)
    
    def __str__(self):
        return f"{self.category.get_name_display()} - {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.end_time:
            self.end_time = self.start_time + timedelta(hours=16)
        if not self.seed:
            self.seed = random.randint(1, 1000000)
        if self.percent_easy + self.percent_medium + self.percent_hard != 100:
            total = self.percent_easy + self.percent_medium + self.percent_hard
            if total > 0:
                self.percent_easy = int((self.percent_easy / total) * 100)
                self.percent_medium = int((self.percent_medium / total) * 100)
                self.percent_hard = 100 - self.percent_easy - self.percent_medium
            else:
                self.percent_easy = 33
                self.percent_medium = 34
                self.percent_hard = 33
        
        super().save(*args, **kwargs)
    
    def is_live(self):
        now = timezone.now()
        return self.is_active and self.start_time <= now <= self.end_time
    
    def time_remaining(self):
        if not self.is_live():
            return timedelta(0)
        return self.end_time - timezone.now()
    
    def get_mcqs(self):
        mcq_pool = MCQ.objects.all()
        
        if self.test_type == 'SUBJECT' and self.subjects.exists():
            print(f"Subject test: Using subjects {list(self.subjects.values_list('name', flat=True))}")
            subject_uids = self.subjects.values_list('uid', flat=True)
            topics = Topic.objects.filter(chapter__unit__subject__uid__in=subject_uids)
            mcq_pool = mcq_pool.filter(topic__in=topics)
            print(f"Filtered to {mcq_pool.count()} MCQs from selected subjects")

        selected_mcqs = []
        remaining_count = self.total_mcqs
        
        # Step 1: Handle MCQ type distribution if specified
        if self.mcq_types_distribution and isinstance(self.mcq_types_distribution, dict):
            type_mcqs = []
            type_remaining = remaining_count
            
            for mcq_type_name, percentage in self.mcq_types_distribution.items():
                # Convert percentage to integer if it's a string
                try:
                    percentage = int(percentage)
                except (ValueError, TypeError):
                    print(f"Warning: Invalid percentage value for type {mcq_type_name}: {percentage}")
                    continue
                
                # Calculate how many MCQs of this type we need
                type_count = int((percentage / 100) * self.total_mcqs)
                if type_count <= 0:
                    continue
                    
                type_remaining -= type_count
                
                try:
                    # Find MCQ type by name (types field contains the type name)
                    mcq_type = mcq_types.objects.get(types=mcq_type_name)
                    # Filter MCQs by this type
                    type_mcq_pool = mcq_pool.filter(types=mcq_type)
                    type_mcq_ids = list(type_mcq_pool.values_list('uid', flat=True))
                    
                    print(f"Found {len(type_mcq_ids)} MCQs of type '{mcq_type_name}' (requested {type_count})")
                    
                    # If we don't have enough MCQs of this type, use what we have
                    if len(type_mcq_ids) < type_count:
                        print(f"Warning: Requested {type_count} MCQs of type {mcq_type_name} but only found {len(type_mcq_ids)}")
                        type_count = len(type_mcq_ids)
                    
                    # Shuffle and select MCQs of this type
                    random.seed(self.seed + hash(mcq_type_name))
                    random.shuffle(type_mcq_ids)
                    type_mcqs.extend(type_mcq_ids[:type_count])
                    
                    print(f"Selected {min(type_count, len(type_mcq_ids))} MCQs of type '{mcq_type_name}'")
                    
                except mcq_types.DoesNotExist:
                    print(f"Warning: MCQ type '{mcq_type_name}' not found in database")
                    # List available types for debugging
                    available_types = list(mcq_types.objects.values_list('types', flat=True))
                    print(f"Available MCQ types: {available_types}")
                    continue
                except Exception as e:
                    print(f"Error processing MCQ type {mcq_type_name}: {e}")
                    continue
            
            # If we need more MCQs to reach the total, get them from the remaining pool
            if type_remaining > 0 and len(type_mcqs) < remaining_count:
                other_mcqs = mcq_pool.exclude(uid__in=type_mcqs)
                other_mcq_ids = list(other_mcqs.values_list('uid', flat=True))
                random.seed(self.seed + 999)  # Different seed for other MCQs
                random.shuffle(other_mcq_ids)
                needed = min(type_remaining, len(other_mcq_ids))
                type_mcqs.extend(other_mcq_ids[:needed])
                print(f"Added {needed} additional MCQs from remaining pool")
            
            # Update selected MCQs and remaining count
            selected_mcqs.extend(type_mcqs)
            remaining_count = self.total_mcqs - len(selected_mcqs)
            print(f"After type distribution: {len(selected_mcqs)} MCQs selected, {remaining_count} remaining")
        
        # Step 2: Handle subject distribution for FULL tests
        subject_mcqs = []
        if self.test_type == 'FULL' and self.subject_distribution and remaining_count > 0:
            subject_mcqs = []
            subject_remaining = remaining_count
            
            # Exclude already selected MCQs
            subject_mcq_pool = mcq_pool
            if selected_mcqs:
                subject_mcq_pool = subject_mcq_pool.exclude(uid__in=selected_mcqs)
            
            for subject_name, percentage in self.subject_distribution.items():
                try:
                    percentage = int(percentage)
                except (ValueError, TypeError):
                    continue
                    
                # Calculate how many MCQs from this subject we need
                count = int((percentage / 100) * remaining_count)
                if count <= 0:
                    continue
                    
                subject_remaining -= count
                
                try:
                    # Find subject by name
                    subject = Subject.objects.get(name=subject_name)
                    topics = Topic.objects.filter(chapter__unit__subject=subject)
                    this_subject_pool = subject_mcq_pool.filter(topic__in=topics)
                    subject_mcq_ids = list(this_subject_pool.values_list('uid', flat=True))
                    
                    # If we don't have enough MCQs from this subject, use what we have
                    if len(subject_mcq_ids) < count:
                        print(f"Warning: Requested {count} MCQs from subject {subject_name} but only found {len(subject_mcq_ids)}")
                        count = len(subject_mcq_ids)
                    
                    # Shuffle and select MCQs from this subject
                    random.seed(self.seed + hash(str(subject.uid)))
                    random.shuffle(subject_mcq_ids)
                    subject_mcqs.extend(subject_mcq_ids[:count])
                    
                except Subject.DoesNotExist:
                    print(f"Warning: Subject {subject_name} not found")
                    continue
            
            # If we need more MCQs to reach the total, get them from the remaining pool
            if subject_remaining > 0 and len(subject_mcqs) < remaining_count:
                other_mcqs = subject_mcq_pool.exclude(uid__in=subject_mcqs)
                other_mcq_ids = list(other_mcqs.values_list('uid', flat=True))
                random.seed(self.seed + 1000)
                random.shuffle(other_mcq_ids)
                needed = min(subject_remaining, len(other_mcq_ids))
                subject_mcqs.extend(other_mcq_ids[:needed])
        
        # Update selected MCQs and remaining count
        selected_mcqs.extend(subject_mcqs)
        remaining_count = self.total_mcqs - len(selected_mcqs)
    
        # Step 3: Handle PYQ filter if needed
        if self.percent_pyq > 0 and remaining_count > 0:
            pyq_count = int((self.percent_pyq / 100) * remaining_count)
            
            # Exclude already selected MCQs
            pyq_mcq_pool = mcq_pool
            if selected_mcqs:
                pyq_mcq_pool = pyq_mcq_pool.exclude(uid__in=selected_mcqs)
            
            pyq_mcqs = list(pyq_mcq_pool.filter(pyq=True).values_list('uid', flat=True))
            non_pyq_mcqs = list(pyq_mcq_pool.filter(pyq=False).values_list('uid', flat=True))
            
            random.seed(self.seed + 2000)
            random.shuffle(pyq_mcqs)
            random.shuffle(non_pyq_mcqs)
            
            # Adjust counts if we don't have enough PYQs
            if len(pyq_mcqs) < pyq_count:
                print(f"Warning: Requested {pyq_count} PYQs but only found {len(pyq_mcqs)}")
                pyq_count = len(pyq_mcqs)
            
            selected_pyq_ids = pyq_mcqs[:pyq_count]
            selected_non_pyq_ids = non_pyq_mcqs[:remaining_count - pyq_count]
            
            selected_mcqs.extend(selected_pyq_ids + selected_non_pyq_ids)
            remaining_count = self.total_mcqs - len(selected_mcqs)
        
        # Step 4: Handle difficulty distribution
        if remaining_count > 0:
            # Calculate how many of each difficulty we need
            easy_count = int((self.percent_easy / 100) * remaining_count)
            medium_count = int((self.percent_medium / 100) * remaining_count)
            hard_count = remaining_count - easy_count - medium_count
            
            # Exclude already selected MCQs
            diff_mcq_pool = mcq_pool
            if selected_mcqs:
                diff_mcq_pool = diff_mcq_pool.exclude(uid__in=selected_mcqs)
            
            # Get difficulty objects
            try:
                easy_diff = difficulties.objects.get(name='Easy')
                medium_diff = difficulties.objects.get(name='Medium')
                hard_diff = difficulties.objects.get(name='Hard')
                
                # Get MCQs of each difficulty
                easy_mcqs = list(diff_mcq_pool.filter(difficulty=easy_diff).values_list('uid', flat=True))
                medium_mcqs = list(diff_mcq_pool.filter(difficulty=medium_diff).values_list('uid', flat=True))
                hard_mcqs = list(diff_mcq_pool.filter(difficulty=hard_diff).values_list('uid', flat=True))
                
                random.seed(self.seed + 3000)
                random.shuffle(easy_mcqs)
                random.shuffle(medium_mcqs)
                random.shuffle(hard_mcqs)
                
                # Add MCQs according to difficulty distribution
                selected_mcqs.extend(easy_mcqs[:easy_count])
                selected_mcqs.extend(medium_mcqs[:medium_count])
                selected_mcqs.extend(hard_mcqs[:hard_count])
                
            except difficulties.DoesNotExist:
                # Fallback if difficulties don't exist
                other_mcqs = list(diff_mcq_pool.values_list('uid', flat=True))
                random.seed(self.seed + 4000)
                random.shuffle(other_mcqs)
                selected_mcqs.extend(other_mcqs[:remaining_count])
        
        # Step 5: If we still need more MCQs, get random ones
        if len(selected_mcqs) < self.total_mcqs:
            remaining_count = self.total_mcqs - len(selected_mcqs)
            other_mcqs = mcq_pool.exclude(uid__in=selected_mcqs)
            other_mcq_ids = list(other_mcqs.values_list('uid', flat=True))
            random.seed(self.seed + 5000)
            random.shuffle(other_mcq_ids)
            selected_mcqs.extend(other_mcq_ids[:remaining_count])
        
        print(f"Final selection: {len(selected_mcqs)} MCQs out of {self.total_mcqs} requested")
        
        # Finally, get the MCQs in the original order
        return MCQ.objects.filter(uid__in=selected_mcqs[:self.total_mcqs])
    
    def populate_test_mcqs(self):
        """
        Populates the MockTestMCQ table with MCQs for this test.
        This will clear existing MCQs and create new ones.
        """
        # Clear existing MCQs for this test
        MockTestMCQ.objects.filter(mock_test=self).delete()
        
        # Get the filtered MCQs
        mcqs = self.get_mcqs()
        
        # Add MCQs with order
        for i, mcq in enumerate(mcqs):
            MockTestMCQ.objects.create(
                mock_test=self,
                mcq=mcq,
                order=i
            )
        
        return len(mcqs)
    
    def get_available_mcq_types(self):
        """
        Helper method to get available MCQ types for this mock test.
        Useful for admin interface or API responses.
        """
        return list(mcq_types.objects.values_list('types', flat=True))
    
    class Meta:
        ordering = ['-start_time']


# Rest of your models remain the same...
class MockTestMCQ(BaseModel):
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='test_mcqs')
    mcq = models.ForeignKey(MCQ, on_delete=models.CASCADE, related_name='mock_tests')
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        unique_together = ('mock_test', 'mcq')
    
    def __str__(self):
        return f"Q{self.order + 1} - {self.mock_test.title}"

class MockSession(BaseModel):
    """
    Represents a user's attempt at a mock test.
    Created when a user starts a mock test.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mock_sessions')
    mock_test = models.ForeignKey('MockTest', on_delete=models.CASCADE, related_name='sessions')
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    
    is_completed = models.BooleanField(default=False)
    is_graded = models.BooleanField(default=False)
    rank = models.PositiveIntegerField(null=True, blank=True)

    # Score details
    total_attempted = models.PositiveIntegerField(default=0)
    total_correct = models.PositiveIntegerField(default=0)
    total_incorrect = models.PositiveIntegerField(default=0)
    total_skipped = models.PositiveIntegerField(default=0)
    
    score = models.FloatField(default=0)
    percentile = models.FloatField(null=True, blank=True)
    
    # Current state
    current_question_index = models.PositiveIntegerField(default=0)
    
    # Flags for test termination
    terminated_by_user = models.BooleanField(default=False)
    terminated_by_timeout = models.BooleanField(default=False)
    terminated_by_browser_close = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('user', 'mock_test')
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.user.username} - {self.mock_test.title}"
    
    def get_time_remaining(self):
        if self.is_completed:
            return 0
        
        elapsed = timezone.now() - self.start_time
        time_limit = timedelta(minutes=self.mock_test.time_limit_minutes)
        remaining = time_limit - elapsed
        
        if remaining.total_seconds() <= 0:
            return 0
        return remaining.total_seconds()
    
    def calculate_score(self):
        if not self.is_completed:
            self.is_completed = True
            self.end_time = timezone.now()
            self.time_spent_seconds = (self.end_time - self.start_time).total_seconds()
        
        # Count stats
        answers = self.answers.all()
        self.total_attempted = answers.exclude(selected_option=None).count()
        self.total_skipped = answers.filter(selected_option=None).count()
        
        correct_count = 0
        incorrect_count = 0
        
        for answer in answers:
            if answer.selected_option is not None:
                if answer.is_correct:
                    correct_count += 1
                else:
                    incorrect_count += 1
        
        self.total_correct = correct_count
        self.total_incorrect = incorrect_count
        
        # Calculate score (using any scoring formula you want)
        # Example: +4 for correct, -1 for incorrect
        self.score = (correct_count * 4) - incorrect_count
        
        self.is_graded = True
        self.save()
        
        # Update mock test stats
        self.mock_test.total_students = self.mock_test.sessions.filter(is_completed=True).count()
        self.mock_test.save()
        try:
            total_participants = self.update_percentile()
            print(f"Successfully updated percentile. Total participants: {total_participants}")
            
        except Exception as e:
        # Log the error but don't let it prevent returning the score
            print(f"Error updating percentile: {e}")
        return self.score
    
    def update_percentile(self):
        """
        Calculate percentile and rank for all completed sessions for the same mock test.
        If scores are equal, the user who completed the test faster gets a higher rank.
        """
        # Get all completed and graded sessions for the same mock test
        all_sessions = MockSession.objects.filter(
            mock_test=self.mock_test,
            is_completed=True,
            is_graded=True
        )
        
        total_participants = all_sessions.count()
        
        if total_participants == 0:
            # Should rarely happen, but handle just in case
            self.percentile = 100.0
            self.rank = 1
            self.save()
            return 1  # Return total participants (1 in this case)
        
        # Convert to list and sort by score (descending) and time spent (ascending)
        # This ensures that for equal scores, faster completion gets higher rank
        sorted_sessions = sorted(
            all_sessions,
            key=lambda s: (-s.score, s.time_spent_seconds)
        )
        
        # Update rank and percentile for all sessions
        for rank, session in enumerate(sorted_sessions, 1):
            # Rank is 1-based (rank 1 is the top performer)
            session.rank = rank
            
            # Calculate percentile (percentage of users who performed worse)
            if total_participants <= 1:
                session.percentile = 100.0
            else:
                # Correctly calculate percentile based on rank
                session.percentile = ((total_participants - rank) / (total_participants - 1)) * 100
            
            # Save the updated session (but not this session since we'll save it outside of the loop)
            if session.uid != self.uid:
                session.save()
        
        # Update the current session's values without saving again
        # (We're iterating through all sessions above, so this one's values have been set)
        # Find the current session in the sorted list to get its updated values
        for session in sorted_sessions:
            if session.uid == self.uid:
                self.rank = session.rank
                self.percentile = session.percentile
                break
        
        # Save the current session
        self.save()
        print(f"Updated percentiles for {total_participants} participants. Current percentile: {self.percentile}")
        
        return total_participants  # Return total participants


class MockAnswer(BaseModel):
    """
    Represents a user's answer to a specific MCQ in a mock test session.
    Created for each MCQ when a user starts a mock test.
    """
    session = models.ForeignKey(MockSession, on_delete=models.CASCADE, related_name='answers')
    mcq = models.ForeignKey(MCQ, on_delete=models.CASCADE, related_name='mock_answers')
    
    # The selected option (A, B, C, D, E)
    selected_option = models.CharField(max_length=100, null=True, blank=True)
    
    # Time tracking
    started_at = models.DateTimeField(auto_now_add=True)
    visible_at = models.DateTimeField(null=True, blank=True)

    answered_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    
    # Flags
    is_marked_for_review = models.BooleanField(default=False)
    is_skipped = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('session', 'mcq')
        ordering = ['session', 'mcq']
    
    def __str__(self):
        return f"Answer by {self.session.user.username} for Q{self.mcq.uid}"
    
    @property
    def is_correct(self):
        if not self.selected_option:
            return False
        return self.selected_option == self.mcq.correct_option
    
    def select_option(self, option):
        """
        Set the selected option and update timestamps.
        """
        self.selected_option = option
        self.answered_at = timezone.now()
        
        # Calculate time spent since the question was last made visible
        if self.visible_at:
            # Only add the time from when the question was last viewed
            elapsed_time = (self.answered_at - self.visible_at).total_seconds()
            self.time_spent_seconds += elapsed_time
        
        self.is_skipped = False
        self.save()
    def mark_visible(self):
        """
        Mark the question as currently visible and update the visible_at timestamp.
        """
        # If the question was previously answered, we don't reset the time_spent
        # Just update the visible_at timestamp for potential additional time
        self.visible_at = timezone.now()
        self.save()
    def nextqueprevtime(self):
        if self.visible_at:
            current_time = timezone.now()
            
            # Check if question was answered after it was made visible
            if self.answered_at and self.answered_at > self.visible_at:
                # If answered after becoming visible, set time_spent directly
                # (don't add to existing time)
                self.time_spent_seconds = (current_time - self.visible_at).total_seconds()
            else:
                # If not answered or answered before becoming visible,
                # add to existing time_spent_seconds
                elapsed_time = (current_time - self.visible_at).total_seconds()
                self.time_spent_seconds += elapsed_time
            
            self.is_skipped = False
        self.save()
        
        self.is_skipped = False
        self.save()
    def mark_for_review(self, marked=True):
        """
        Mark or unmark this question for review.
        """
        self.is_marked_for_review = marked
        self.save()
    
    def skip(self):
        """
        Mark this question as skipped.
        """
        self.is_skipped = True
        self.save()