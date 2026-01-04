from django.contrib import admin
from .models import Profile,Feedback,Contact,VisitorCount,Notification,MedicalCollege,State
from django.utils.html import format_html  # Add this import at the top
from django.utils.safestring import mark_safe  # Add this import as well
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import AppVersion

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    ordering = ('-date_joined',)  # This will order users from newest to oldest

# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Register your models here.
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'is_email_verified', 'medical_college','other_medical_college',
        'current_test', 'hive_current_test', 'mock_current_test'
    )
    list_filter = ('is_email_verified', 'medical_college')
    search_fields = ('user__username', 'user__email', 'medical_college__name')
    autocomplete_fields = ['user', 'medical_college']
    ordering = ('user__username',)
    readonly_fields = ('email_token', 'reset_token')
    list_per_page = 50
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        'user_info', 
        'category', 
        'rating_stars', 
        'status', 
        'created_at', 
        'reviewed_by',
        'reviewed_at'
    )
    list_filter = ('status', 'category', 'rating', 'created_at', 'reviewed_by')
    search_fields = ('user__username', 'user__email', 'message', 'admin_notes')
    readonly_fields = ('created_at', 'updated_at', 'reviewed_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'category', 'rating')
        }),
        ('Feedback Content', {
            'fields': ('message',)
        }),
        ('Admin Section', {
            'fields': ('status', 'admin_notes', 'admin_response', 'reviewed_by', 'reviewed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def user_info(self, obj):
        return format_html(
            '<strong>{}</strong><br><small>{}</small>',
            obj.user.username,
            obj.user.email
        )
    user_info.short_description = 'User'

    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html(
            '<span style="color: #fbbf24;">{}</span>',
            stars
        )
    rating_stars.short_description = 'Rating'

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data and not obj.reviewed_by:
            obj.mark_as_reviewed(request.user)
        super().save_model(request, obj, form, change)

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at', 'is_resolved')
    list_filter = ('subject', 'is_resolved', 'created_at')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('created_at',)
    list_per_page = 20
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('name', 'email', 'user')
        }),
        ('Message Details', {
            'fields': ('subject', 'message')
        }),
        ('Status', {
            'fields': ('is_resolved', 'created_at')
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # Only for new objects
            if obj.user and not obj.name:
                obj.name = obj.user.username
            if obj.user and not obj.email:
                obj.email = obj.user.email
        super().save_model(request, obj, form, change)


@admin.register(VisitorCount)
class VisitorCountAdmin(admin.ModelAdmin):
    list_display = ('path', 'count', 'last_visit')
    list_filter = ('last_visit',)
    search_fields = ('path',)
    readonly_fields = ('count', 'last_visit')
    ordering = ('-count',)
    
    def has_add_permission(self, request):
        # Prevent manual creation of entries
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Allow deletion of records if needed
        return True
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    # Custom admin page header
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Website Traffic Statistics'
        return super().changelist_view(request, extra_context=extra_context)

admin.site.register(Notification)
@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(MedicalCollege)
class MedicalCollegeAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'location', 'state', 'established', 'university', 'ownership'
    )
    list_filter = ('state', 'ownership', 'established')
    search_fields = ('name', 'location', 'university')
    ordering = ('state__name', 'name')
    autocomplete_fields = ['state']
    list_per_page = 50



@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = [
        'platform', 
        'current_version', 
        'show_download_banner',
        'has_apk_file', 
        'force_update', 
        'is_maintenance',
        'updated_at'
    ]
    list_filter = ['platform', 'force_update', 'is_maintenance', 'show_download_banner']
    search_fields = ['current_version', 'whats_new']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('platform', 'current_version', 'minimum_version')
        }),
        ('Download Settings', {
            'fields': ('apk_file', 'download_url'),
            'description': 'Upload APK file directly or provide an external download URL'
        }),
        ('Banner Settings', {
            'fields': ('show_download_banner', 'banner_text'),
        }),
        ('Update Configuration', {
            'fields': ('force_update', 'update_message', 'whats_new')
        }),
        ('Maintenance Mode', {
            'fields': ('is_maintenance', 'maintenance_message'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def has_apk_file(self, obj):
        return bool(obj.apk_file)
    has_apk_file.boolean = True
    has_apk_file.short_description = 'APK Uploaded'