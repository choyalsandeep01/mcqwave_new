from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from django.forms import Textarea
from .models import Subject, Unit, difficulties, mcq_types, PYQ

# Custom admin configuration
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('order', 'name', 'display_icon', 'icon_color', 'total_units', 'total_pyqs', 'created_at')
    list_display_links = ('name',)
    list_editable = ('order',)
    list_filter = ('created_at', 'updated_at')
    search_fields = ('name', 'icon')
    ordering = ('order', 'name')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'order')
        }),
        ('Icon Settings', {
            'fields': ('icon', 'icon_color'),
            'description': 'Choose an icon and color for this subject'
        }),
    )
    
    def display_icon(self, obj):
        """Display the icon in the admin list"""
        return format_html(obj.get_icon_html())
    display_icon.short_description = 'Icon'
    
    def total_units(self, obj):
        """Display total units count"""
        return obj.units.count()
    total_units.short_description = 'Units'
    
    def total_pyqs(self, obj):
        """Display total PYQs count"""
        return PYQ.objects.filter(unit__subject=obj).count()
    total_pyqs.short_description = 'PYQs'


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'order', 'total_pyqs', 'created_at')
    list_display_links = ('name',)
    list_editable = ('order',)
    list_filter = ('subject', 'created_at', 'updated_at')
    search_fields = ('name', 'subject__name')
    ordering = ('subject', 'order', 'name')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('subject', 'name', 'order')
        }),
    )
    
    def total_pyqs(self, obj):
        """Display total PYQs count for this unit"""
        return obj.pyqs.count()
    total_pyqs.short_description = 'PYQs'


@admin.register(difficulties)
class DifficultiesAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_pyqs', 'created_at')
    list_display_links = ('name',)
    search_fields = ('name',)
    ordering = ('name',)
    
    def total_pyqs(self, obj):
        """Display total PYQs count for this difficulty"""
        return obj.pyq_difficulty.count()
    total_pyqs.short_description = 'PYQs'


@admin.register(mcq_types)
class McqTypesAdmin(admin.ModelAdmin):
    list_display = ('types', 'total_pyqs', 'created_at')
    list_display_links = ('types',)
    search_fields = ('types',)
    ordering = ('types',)
    
    def total_pyqs(self, obj):
        """Display total PYQs count for this type"""
        return obj.pyq_type.count()
    total_pyqs.short_description = 'PYQs'


@admin.register(PYQ)
class PYQAdmin(admin.ModelAdmin):
    list_display = (
        'pyqcode', 'get_short_text', 'unit', 'topic', 'get_subject', 'difficulty', 'types', 
        'get_exam_display', 'hig_yield', 'correct_attempts', 'incorrect_attempts', 
        'success_rate', 'created_at'
    )
    list_display_links = ('get_short_text',)
    list_filter = (
        'unit__subject', 'unit', 'difficulty', 'types', 'pyq_cat', 'pyq_year', 'pyq_month',
        'hig_yield', 'pyq', 'created_at'
    )
    search_fields = ('text', 'pyqcode', 'topic', 'option_1', 'option_2', 'option_3', 'option_4')
    ordering = ('-created_at',)
    list_per_page = 25
    
    fieldsets = (
        ('Bulk Input', {
            'fields': ('bulk_input',),
            'description': 'Format: question|option1|option2|option3|option4|correct_option|explanation',
            'classes': ('wide',)
        }),
        ('Question Details', {
            'fields': ('unit', 'topic', 'text', 'image')
        }),
        ('Options', {
            'fields': ('option_1', 'option_2', 'option_3', 'option_4', 'correct_option'),
            'classes': ('wide',)
        }),
        ('Answer & Explanation', {
            'fields': ('explanation',),
            'classes': ('wide',)
        }),
        ('Classification', {
            'fields': ('difficulty', 'types', 'pyqcode'),
            'classes': ('wide',)
        }),
        ('PYQ Information', {
            'fields': ('pyq', 'pyq_cat', 'pyq_year', 'pyq_month', 'hig_yield'),
            'classes': ('wide',),
            'description': 'Month is optional and mainly for INI-CET and FMGE exams that occur multiple times per year'
        }),
        ('Statistics', {
            'fields': ('correct_attempts', 'incorrect_attempts'),
            'classes': ('collapse',)
        }),
    )
    
    # Custom form widgets for better text editing
    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows': 4, 'cols': 80})},
    }
    
    # Read-only fields that are calculated
    readonly_fields = ('success_rate_display',)
    
    def get_short_text(self, obj):
        """Display shortened question text"""
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    get_short_text.short_description = 'Question'
    
    def get_subject(self, obj):
        """Display subject name"""
        return obj.unit.subject.name if obj.unit else '-'
    get_subject.short_description = 'Subject'
    get_subject.admin_order_field = 'unit__subject__name'
    
    def get_exam_display(self, obj):
        """Display formatted exam information with month if applicable"""
        return obj.get_exam_display() or '-'
    get_exam_display.short_description = 'Exam'
    get_exam_display.admin_order_field = 'pyq_cat'
    
    def success_rate(self, obj):
        """Calculate and display success rate"""
        # Explicitly convert to integers to avoid SafeString issues
        try:
            correct = int(obj.correct_attempts) if obj.correct_attempts else 0
            incorrect = int(obj.incorrect_attempts) if obj.incorrect_attempts else 0
            total = correct + incorrect
            
            if total == 0:
                return "No attempts"
                
            rate = (correct / total) * 100
            color = 'green' if rate >= 70 else 'orange' if rate >= 40 else 'red'
            
            return format_html(
                '<span style="color: {};">{:.1f}%</span>',
                color, rate
            )
        except (ValueError, TypeError) as e:
            return "Error calculating rate"
    success_rate.short_description = 'Success Rate'

    
    def success_rate_display(self, obj):
        """Detailed success rate for form"""
        try:
            correct = int(obj.correct_attempts) if obj.correct_attempts else 0
            incorrect = int(obj.incorrect_attempts) if obj.incorrect_attempts else 0
            total = correct + incorrect
            
            if total == 0:
                return "No attempts yet"
                
            rate = (correct / total) * 100
            return f"{rate:.1f}% ({correct}/{total})"
        except (ValueError, TypeError):
            return "Error calculating rate"
    success_rate_display.short_description = 'Success Rate'
    
    def mark_as_high_yield(self, request, queryset):
        """Mark selected PYQs as high yield"""
        updated = queryset.update(hig_yield=True)
        self.message_user(request, f'{updated} PYQs marked as high yield.')
    mark_as_high_yield.short_description = "Mark selected PYQs as high yield"
    
    def unmark_as_high_yield(self, request, queryset):
        """Unmark selected PYQs as high yield"""
        updated = queryset.update(hig_yield=False)
        self.message_user(request, f'{updated} PYQs unmarked as high yield.')
    unmark_as_high_yield.short_description = "Unmark selected PYQs as high yield"
    
    def reset_attempts(self, request, queryset):
        """Reset attempt statistics for selected PYQs"""
        updated = queryset.update(correct_attempts=0, incorrect_attempts=0)
        self.message_user(request, f'Attempt statistics reset for {updated} PYQs.')
    reset_attempts.short_description = "Reset attempt statistics"
    
    def bulk_set_exam_details(self, request, queryset):
        """Custom action to bulk set exam category, year, and month"""
        # This would need a custom intermediate page - for now just a placeholder
        self.message_user(request, 'Bulk exam details update - implement custom form for this action.')
    bulk_set_exam_details.short_description = "Bulk set exam category/year/month"
    
    # Enhanced save model
    def save_model(self, request, obj, form, change):
        """Custom save to handle bulk input"""
        super().save_model(request, obj, form, change)
        # The bulk input processing is handled in the model's save method



# Add some custom CSS for better appearance
class Media:
    css = {
        'all': ('admin/css/custom_admin.css',)
    }

from django.contrib import admin
from django.utils.html import format_html
from .models import PYQBookmark


@admin.register(PYQBookmark)
class PYQBookmarkAdmin(admin.ModelAdmin):
    list_display = (
        'bkmk_id', 'user', 'get_pyq_text', 'bookmark_type', 'created_at'
    )
    list_display_links = ('bkmk_id',)
    list_filter = ('bookmark_type', 'created_at', 'user')
    search_fields = ('bkmk_id', 'user__username', 'pyq__text')
    ordering = ('-created_at',)
    list_per_page = 25
    
    # Simple display methods
    def get_pyq_text(self, obj):
        """Display shortened PYQ text"""
        if obj.pyq and obj.pyq.text:
            return obj.pyq.text[:60] + '...' if len(obj.pyq.text) > 60 else obj.pyq.text
        return '-'
    get_pyq_text.short_description = 'PYQ Question'
    
    # Simple actions
    actions = ['change_to_star', 'change_to_unstudied', 'change_to_other']
    
    def change_to_star(self, request, queryset):
        updated = queryset.update(bookmark_type='Star')
        self.message_user(request, f'{updated} bookmarks changed to Star.')
    change_to_star.short_description = "Change to Star"
    
    def change_to_unstudied(self, request, queryset):
        updated = queryset.update(bookmark_type='Unstudied')
        self.message_user(request, f'{updated} bookmarks changed to Unstudied.')
    change_to_unstudied.short_description = "Change to Unstudied"
    
    def change_to_other(self, request, queryset):
        updated = queryset.update(bookmark_type='Other')
        self.message_user(request, f'{updated} bookmarks changed to Other.')
    change_to_other.short_description = "Change to Other"
    
    # Auto-generate bkmk_id if not provided
    def save_model(self, request, obj, form, change):
        if not obj.bkmk_id:
            import uuid
            obj.bkmk_id = str(uuid.uuid4())
        super().save_model(request, obj, form, change)
