from django.contrib import admin
from django.db.models import Count, Avg
from django.utils.html import format_html
from .models import (
    Subject, Unit, Topic, Flashcard, UserFlashcardProgress,
    UserStreak, Badge, UserBadge, StudySession
)

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'color_badge', 'display_order', 'units_count', 'flashcards_count', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    ordering = ['display_order', 'name']
    list_editable = ['display_order', 'is_active']
    
    def color_badge(self, obj):
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 5px;">{}</span>',
            obj.color, obj.color
        )
    color_badge.short_description = 'Color'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            _units_count=Count('units', distinct=True),
            _flashcards_count=Count('units__topics__flashcards', distinct=True)
        )
    
    def units_count(self, obj):
        return obj._units_count
    units_count.short_description = 'Units'
    units_count.admin_order_field = '_units_count'
    
    def flashcards_count(self, obj):
        return obj._flashcards_count
    flashcards_count.short_description = 'Flashcards'
    flashcards_count.admin_order_field = '_flashcards_count'

@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['name', 'subject', 'display_order', 'topics_count', 'flashcards_count', 'is_active']
    list_filter = ['is_active', 'subject', 'created_at']
    search_fields = ['name', 'subject__name']
    ordering = ['subject', 'display_order', 'name']
    list_editable = ['display_order', 'is_active']
    autocomplete_fields = ['subject']
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('subject').annotate(
            _topics_count=Count('topics', distinct=True),
            _flashcards_count=Count('topics__flashcards', distinct=True)
        )
    
    def topics_count(self, obj):
        return obj._topics_count
    topics_count.short_description = 'Topics'
    
    def flashcards_count(self, obj):
        return obj._flashcards_count
    flashcards_count.short_description = 'Flashcards'

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ['name', 'unit', 'subject_name', 'display_order', 'flashcards_count', 'is_active']
    list_filter = ['is_active', 'unit__subject', 'unit', 'created_at']
    search_fields = ['name', 'unit__name', 'unit__subject__name']
    ordering = ['unit__subject', 'unit', 'display_order', 'name']
    list_editable = ['display_order', 'is_active']
    autocomplete_fields = ['unit']
    
    def subject_name(self, obj):
        return obj.unit.subject.name
    subject_name.short_description = 'Subject'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('unit__subject').annotate(
            _flashcards_count=Count('flashcards', distinct=True)
        )
    
    def flashcards_count(self, obj):
        return obj._flashcards_count
    flashcards_count.short_description = 'Flashcards'

@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ['front_text_short', 'topic', 'card_type', 'difficulty', 'has_images', 'linked_mcqs_count', 'is_active', 'created_at']
    list_filter = ['card_type', 'difficulty', 'is_active', 'topic__unit__subject', 'created_at']
    search_fields = ['front_text', 'back_text', 'topic__name', 'mnemonic']
    ordering = ['-created_at']
    list_editable = ['is_active']
    autocomplete_fields = ['topic']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('topic', 'card_type', 'difficulty', 'is_active')
        }),
        ('Front Side', {
            'fields': ('front_text', 'front_image')
        }),
        ('Back Side', {
            'fields': ('back_text', 'back_image', 'mnemonic', 'key_points', 'references')
        }),
        ('Linked Content', {
            'fields': ('linked_mcq_uids',),
            'classes': ('collapse',)
        }),
    )
    
    def front_text_short(self, obj):
        return obj.front_text[:60] + '...' if len(obj.front_text) > 60 else obj.front_text
    front_text_short.short_description = 'Front Text'
    
    def has_images(self, obj):
        front = '🖼️' if obj.front_image else ''
        back = '🖼️' if obj.back_image else ''
        return format_html('{} {}', front, back) if front or back else '-'
    has_images.short_description = 'Images'
    
    def linked_mcqs_count(self, obj):
        return len(obj.linked_mcq_uids) if obj.linked_mcq_uids else 0
    linked_mcqs_count.short_description = 'MCQs'

@admin.register(UserFlashcardProgress)
class UserFlashcardProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'flashcard_preview', 'status', 'ease_factor', 'repetitions', 'interval_days', 'accuracy_percent', 'is_due_today', 'next_review']
    list_filter = ['status', 'last_rating', 'next_review', 'created_at']
    search_fields = ['user__username', 'user__email', 'flashcard__front_text']
    readonly_fields = ['created_at', 'updated_at', 'accuracy', 'is_due']
    ordering = ['-updated_at']
    
    fieldsets = (
        ('User & Card', {
            'fields': ('user', 'flashcard')
        }),
        ('SM-2 Algorithm', {
            'fields': ('ease_factor', 'repetitions', 'interval', 'status', 'last_rating')
        }),
        ('Review Schedule', {
            'fields': ('last_reviewed', 'next_review', 'is_due')
        }),
        ('Statistics', {
            'fields': ('total_reviews', 'correct_reviews', 'accuracy')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def flashcard_preview(self, obj):
        text = obj.flashcard.front_text[:40] + '...' if len(obj.flashcard.front_text) > 40 else obj.flashcard.front_text
        return text
    flashcard_preview.short_description = 'Flashcard'
    
    def interval_days(self, obj):
        return f"{obj.interval} days"
    interval_days.short_description = 'Interval'
    
    def accuracy_percent(self, obj):
        return f"{obj.accuracy:.1f}%"
    accuracy_percent.short_description = 'Accuracy'
    
    def is_due_today(self, obj):
        return obj.is_due  # Return boolean, not emoji
    is_due_today.short_description = 'Due'
    is_due_today.boolean = True  # Now this works correctly


@admin.register(UserStreak)
class UserStreakAdmin(admin.ModelAdmin):
    list_display = ['user', 'current_streak', 'longest_streak', 'last_study_date', 'total_xp', 'total_cards_studied', 'updated_at']
    list_filter = ['last_study_date', 'updated_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-current_streak']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon_display', 'color_badge', 'criteria_type', 'criteria_value', 'xp_reward', 'users_earned']
    list_filter = ['criteria_type', 'subject']
    search_fields = ['name', 'description']
    ordering = ['criteria_type', 'criteria_value']
    
    def icon_display(self, obj):
        return format_html('<span style="font-size: 24px;">{}</span>', obj.icon)
    icon_display.short_description = 'Icon'
    
    def color_badge(self, obj):
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 5px;">{}</span>',
            obj.color, obj.color
        )
    color_badge.short_description = 'Color'
    
    def users_earned(self, obj):
        return UserBadge.objects.filter(badge=obj).count()
    users_earned.short_description = 'Users Earned'

@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ['user', 'badge', 'badge_icon', 'earned_at']
    list_filter = ['badge', 'earned_at']
    search_fields = ['user__username', 'user__email', 'badge__name']
    readonly_fields = ['earned_at']
    ordering = ['-earned_at']
    
    def badge_icon(self, obj):
        return format_html(
            '<span style="font-size: 20px; color: {};">{}</span>',
            obj.badge.color, obj.badge.icon
        )
    badge_icon.short_description = 'Icon'

@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'cards_reviewed', 'accuracy_percent', 'duration_display', 'xp_earned', 'started_at', 'status']
    list_filter = ['started_at', 'ended_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['started_at']
    ordering = ['-started_at']
    
    def accuracy_percent(self, obj):
        if obj.cards_reviewed == 0:
            return '0%'
        return f"{(obj.cards_correct / obj.cards_reviewed * 100):.1f}%"
    accuracy_percent.short_description = 'Accuracy'
    
    def duration_display(self, obj):
        minutes = obj.duration_seconds // 60
        seconds = obj.duration_seconds % 60
        return f"{minutes}m {seconds}s"
    duration_display.short_description = 'Duration'
    
    def status(self, obj):
        return '✅ Completed' if obj.ended_at else '⏳ In Progress'
    status.short_description = 'Status'
