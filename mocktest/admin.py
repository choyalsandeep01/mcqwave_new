from django.contrib import admin
from .models import MockTestCategory, MockTest, MockTestMCQ,  MockAnswer, MockSession
from django.utils.html import format_html
from django.contrib import messages  # Add this import

admin.site.site_header = "MCQwave Administration"
admin.site.site_title = "MCQwave Admin Portal"
admin.site.index_title = "Welcome to MCQwave Admin Panel"

@admin.register(MockTestCategory)
class MockTestCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name',)

@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ('uid', 'title', 'category', 'test_type', 'start_time', 'end_time', 'is_active', 'total_mcqs')
    list_filter = ('category', 'test_type', 'is_active')
    search_fields = ('title',)
    readonly_fields = ('seed',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('category', 'title', 'description', 'test_type', 'subjects','total_students')
        }),
        ('Time Settings', {
            'fields': ('start_time', 'end_time', 'time_limit_minutes')
        }),
        ('MCQ Selection Criteria', {
            'fields': ('total_mcqs', 'percent_pyq', 'percent_easy', 'percent_medium', 'percent_hard', 'mcq_types_distribution', 'subject_distribution')
        }),
        ('Correctness Filters', {
            'fields': ('percent_most_correct', 'percent_most_incorrect')
        }),
        ('Miscellaneous', {
            'fields': ('is_active', 'seed')
        })
    )
    filter_horizontal = ('subjects',)  # This makes the subjects selection more user-friendly
    actions = ['refresh_all_session_percentiles']
    def refresh_all_session_percentiles(self, request, queryset):
        total_updated = 0
        for mock_test in queryset:
            sessions = MockSession.objects.filter(
                mock_test=mock_test,
                is_completed=True,
                is_graded=True
            )
            
            # Sort sessions by score (descending) and time spent (ascending)
            sorted_sessions = sorted(
                sessions,
                key=lambda s: (-s.score, s.time_spent_seconds)
            )
            
            total_participants = len(sorted_sessions)
            if total_participants == 0:
                continue
                
            # Assign ranks
            for rank, session in enumerate(sorted_sessions, 1):
                # Calculate percentile
                if total_participants <= 1:
                    percentile = 100.0
                else:
                    percentile = ((total_participants - rank) / (total_participants - 1)) * 100
                
                # Update session
                session.rank = rank
                session.percentile = percentile
                session.save()
                total_updated += 1
        
        self.message_user(
            request,
            f"Successfully refreshed ranks and percentiles for {total_updated} sessions across {queryset.count()} mock tests.",
            messages.SUCCESS
        )
    
    refresh_all_session_percentiles.short_description = "Refresh ranks and percentiles for selected mock tests"
    def save_related(self, request, form, formsets, change):
        """
        Save related objects after the main object is saved.
        This ensures M2M relationships are saved before calling populate_test_mcqs().
        """
        super().save_related(request, form, formsets, change)
        # After all related objects are saved (including M2M), populate the MCQs
        form.instance.populate_test_mcqs()

@admin.register(MockTestMCQ)
class MockTestMCQAdmin(admin.ModelAdmin):
    list_display = ('mock_test', 'mcq', 'order')
    list_filter = ('mock_test',)
    search_fields = ('mock_test__title', 'mcq__question')
    ordering = ('mock_test', 'order')

class MockAnswerInline(admin.TabularInline):
    model = MockAnswer
    extra = 0
    readonly_fields = ('mcq', 'selected_option', 'is_correct', 'time_spent_seconds', 'is_marked_for_review', 'is_skipped')
    fields = ('mcq', 'selected_option', 'is_correct', 'time_spent_seconds', 'is_marked_for_review', 'is_skipped')
    can_delete = False
    max_num = 0  # Don't allow adding new answers via admin
    show_change_link = True
    
    def is_correct(self, obj):
        if obj.selected_option is None:
            return None
        is_correct = obj.selected_option == obj.mcq.correct_option
        return format_html(
            '<span style="color: {};">{}</span>',
            'green' if is_correct else 'red',
            '✓' if is_correct else '✗'
        )
    is_correct.short_description = 'Correct'

# MockSession Admin
@admin.register(MockSession)
class MockSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'mock_test', 'start_time', 'end_time', 'score', 'rank','percentile', 
                    'is_completed', 'is_graded', 'time_spent_display')
    list_filter = ('is_completed', 'is_graded', 'mock_test__category', 'mock_test')
    search_fields = ('user__username', 'mock_test__title')
    readonly_fields = ('user', 'mock_test', 'start_time', 'end_time', 'time_spent_seconds',
                      'score', 'percentile', 'total_attempted', 'total_correct', 
                      'total_incorrect', 'total_skipped', 'current_question_index',
                      'terminated_by_user', 'terminated_by_timeout', 'terminated_by_browser_close',
                      'score_summary', 'completion_status')
    fieldsets = (
        ('Session Info', {
            'fields': ('user', 'mock_test', 'start_time', 'end_time', 'time_spent_seconds')
        }),
        ('Completion Status', {
            'fields': ('is_completed', 'is_graded', 'terminated_by_user', 
                       'terminated_by_timeout', 'terminated_by_browser_close',
                       'completion_status')
        }),
        ('Performance', {
            'fields': ('score', 'percentile', 'score_summary')
        }),
        ('Question Stats', {
            'fields': ('total_attempted', 'total_correct', 'total_incorrect', 'total_skipped', 
                       'current_question_index')
        }),
    )
    inlines = [MockAnswerInline]
    
    def time_spent_display(self, obj):
        minutes, seconds = divmod(obj.time_spent_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        return f"{minutes}m {seconds}s"
    time_spent_display.short_description = 'Time Spent'
    
    def score_summary(self, obj):
        if not obj.is_graded:
            return "Not graded yet"
        
        correct_points = obj.total_correct * 4
        incorrect_points = obj.total_incorrect * -1
        
        return format_html(
            '<div style="margin-bottom: 5px;">'
            'Correct: {} × 4 = {}</div>'
            '<div style="margin-bottom: 5px;">'
            'Incorrect: {} × (-1) = {}</div>'
            '<div style="margin-bottom: 5px;">'
            'Skipped: {} × 0 = 0</div>'
            '<div style="font-weight: bold; margin-top: 5px; padding-top: 5px; border-top: 1px solid #eee;">'
            'Total Score: {}</div>',
            obj.total_correct, correct_points,
            obj.total_incorrect, incorrect_points,
            obj.total_skipped,
            obj.score
        )
    score_summary.short_description = 'Score Breakdown'
    
    def completion_status(self, obj):
        if not obj.is_completed:
            return format_html('<span style="color: blue;">In Progress</span>')
        
        if obj.terminated_by_timeout:
            reason = "Time limit exceeded"
        elif obj.terminated_by_user:
            reason = "Submitted by user"
        elif obj.terminated_by_browser_close:
            reason = "Browser closed"
        else:
            reason = "Completed"
            
        return format_html('<span style="color: green;">{}</span>', reason)
    completion_status.short_description = 'Completion Reason'
    
    def has_add_permission(self, request):
        return False  # Sessions should only be created through the app

# MockAnswer Admin
@admin.register(MockAnswer)
class MockAnswerAdmin(admin.ModelAdmin):
    list_display = ('mcq_question', 'session_user', 'selected_option','visible_at', 'answered_at', 'is_correct_display', 
                   'time_spent_display', 'is_marked_for_review', 'is_skipped')
    list_filter = ('is_marked_for_review', 'is_skipped', 'session__mock_test')
    search_fields = ('session__user__username', 'mcq__text')
    readonly_fields = ('session', 'mcq', 'mcq_display', 'selected_option', 'started_at','visible_at', 
                      'answered_at', 'time_spent_seconds', 'is_correct_display')
    
    fieldsets = (
        ('Answer Info', {
            'fields': ('session', 'mcq', 'mcq_display')
        }),
        ('Response', {
            'fields': ('selected_option', 'is_correct_display', 'started_at','visible_at', 'answered_at', 
                      'time_spent_seconds', 'is_marked_for_review', 'is_skipped')
        }),
    )
    
    def mcq_question(self, obj):
        return obj.mcq.text[:50] + '...' if len(obj.mcq.text) > 50 else obj.mcq.text
    mcq_question.short_description = 'Question'
    
    def session_user(self, obj):
        return obj.session.user.username
    session_user.short_description = 'User'
    
    def is_correct_display(self, obj):
        if obj.selected_option is None:
            return format_html('<span style="color: gray;">Not answered</span>')
        
        is_correct = obj.selected_option == obj.mcq.correct_option
        return format_html(
            '<span style="color: {};">{}</span>',
            'green' if is_correct else 'red',
            '✓' if is_correct else '✗'
        )
    is_correct_display.short_description = 'Correct'
    
    def time_spent_display(self, obj):
        minutes, seconds = divmod(obj.time_spent_seconds, 60)
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    time_spent_display.short_description = 'Time Spent'
    
    def mcq_display(self, obj):
        correct = obj.mcq.correct_option
        options = {
            'A': obj.mcq.option_a,
            'B': obj.mcq.option_b,
            'C': obj.mcq.option_c,
            'D': obj.mcq.option_d,
        }
        if hasattr(obj.mcq, 'option_e') and obj.mcq.option_e:
            options['E'] = obj.mcq.option_e
            
        html = f'<p><strong>Question:</strong> {obj.mcq.question_text}</p><ul>'
        
        for key, option in options.items():
            if option:
                style = ""
                if key == correct:
                    style = 'color: green; font-weight: bold;'
                elif key == obj.selected_option:
                    style = 'color: red; font-weight: bold;'
                    
                html += f'<li style="{style}">Option {key}: {option}</li>'
                
        html += '</ul>'
        return format_html(html)
    mcq_display.short_description = 'MCQ Details'
    
    def has_add_permission(self, request):
        return False  # Answers should only be created through the app
