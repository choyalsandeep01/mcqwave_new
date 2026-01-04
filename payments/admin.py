from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta
import json
from .models import PaymentPlan, PaymentTransaction, UserSubscription, ActivePlanConfiguration

@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'category_display', 'plan_type_display', 'price_display', 
        'duration_days', 'discount_display', 'status_indicators', 'is_active'
    ]
    list_filter = [
        'category', 'plan_type', 'is_active', 'is_most_popular', 'is_best_value',
        'created_at'
    ]
    search_fields = ['name', 'description']
    ordering = ['category', 'duration_days', 'price']
    readonly_fields = ['uid', 'created_at', 'updated_at', 'monthly_price_display']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'plan_type', 'description')
        }),
        ('Pricing', {
            'fields': ('price', 'discount_percentage', 'duration_days', 'monthly_price_display'),
            'description': 'Set pricing and discount information'
        }),
        ('Features & Benefits', {
            'fields': ('features',),
            'description': 'Add features as a JSON list, e.g., ["Feature 1", "Feature 2"]'
        }),
        ('Visibility & Marketing', {
            'fields': ('is_active', 'is_most_popular', 'is_best_value'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('uid', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def category_display(self, obj):
        if not obj or not obj.category:
            return '—'
        
        category_colors = {
            'neet_pg_inicet': '#3b82f6',
            'fmge': '#dc2626', 
            'upsc_cms': '#059669'
        }
        color = category_colors.get(obj.category, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; '
            'border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_category_display()
        )
    category_display.short_description = 'Category'
    category_display.admin_order_field = 'category'
    
    def plan_type_display(self, obj):
        if not obj or not obj.plan_type:
            return '—'
        return obj.get_plan_type_display()
    plan_type_display.short_description = 'Plan Type'
    plan_type_display.admin_order_field = 'plan_type'
    
    def price_display(self, obj):
        if not obj or obj.price is None:
            return '—'
        return format_html(
            '<strong style="color: #059669;">₹{}</strong>',
            obj.price
        )
    price_display.short_description = 'Price'
    price_display.admin_order_field = 'price'
    
    def discount_display(self, obj):
        if not obj:
            return '—'
        
        # Handle None values and ensure safe comparison
        discount = getattr(obj, 'discount_percentage', None)
        if discount is None:
            return '—'
            
        try:
            discount_float = float(discount)
            if discount_float <= 0:
                return '—'
            return format_html(
                '<span style="background-color: #10b981; color: white; padding: 2px 6px; '
                'border-radius: 8px; font-size: 10px;">{}%</span>',
                discount
            )
        except (TypeError, ValueError):
            return '—'
    discount_display.short_description = 'Discount'
    
    def status_indicators(self, obj):
        if not obj:
            return '—'
        
        indicators = []
        if getattr(obj, 'is_most_popular', False):
            indicators.append('<span style="color: #f59e0b;">⭐ Popular</span>')
        if getattr(obj, 'is_best_value', False):
            indicators.append('<span style="color: #dc2626;">🔥 Best Value</span>')
        if not getattr(obj, 'is_active', True):
            indicators.append('<span style="color: #6b7280;">❌ Inactive</span>')
        return mark_safe(' '.join(indicators)) if indicators else '—'
    status_indicators.short_description = 'Status'
    
    def monthly_price_display(self, obj):
        if not obj:
            return '—'
        
        # Check if required fields exist and have values
        if not hasattr(obj, 'price') or not hasattr(obj, 'duration_days'):
            return '—'
            
        if obj.price is None or obj.duration_days is None:
            return '—'
            
        try:
            # Calculate monthly price manually to avoid issues with the property
            price = float(obj.price)
            duration_days = int(obj.duration_days)
            
            if duration_days <= 0:
                return '—'
            
            if duration_days <= 30:
                monthly_price = price
            elif duration_days <= 90:  # 3 months
                monthly_price = price / 3
            elif duration_days <= 180:  # 6 months
                monthly_price = price / 6
            else:  # 12 months
                monthly_price = price / 12
            
            return f"₹{monthly_price:.2f}/month"
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            return '—'
    monthly_price_display.short_description = 'Monthly Equivalent'
    
    actions = ['activate_plans', 'deactivate_plans', 'mark_most_popular', 'mark_best_value']
    
    def activate_plans(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} plans activated successfully.')
    activate_plans.short_description = 'Activate selected plans'
    
    def deactivate_plans(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} plans deactivated successfully.')
    deactivate_plans.short_description = 'Deactivate selected plans'
    
    def mark_most_popular(self, request, queryset):
        # First, remove most_popular from all plans in same category
        for plan in queryset:
            if plan and plan.category:
                PaymentPlan.objects.filter(category=plan.category).update(is_most_popular=False)
                plan.is_most_popular = True
                plan.save()
        self.message_user(request, 'Selected plans marked as most popular.')
    mark_most_popular.short_description = 'Mark as most popular'
    
    def mark_best_value(self, request, queryset):
        # First, remove best_value from all plans in same category
        for plan in queryset:
            if plan and plan.category:
                PaymentPlan.objects.filter(category=plan.category).update(is_best_value=False)
                plan.is_best_value = True
                plan.save()
        self.message_user(request, 'Selected plans marked as best value.')
    mark_best_value.short_description = 'Mark as best value'


@admin.register(ActivePlanConfiguration)
class ActivePlanConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'plan_name', 'plan_category', 'is_visible', 'display_order', 
        'custom_badge_display', 'promotional_text'
    ]
    list_filter = ['is_visible', 'plan__category', 'plan__plan_type']
    search_fields = ['plan__name', 'custom_badge_text', 'promotional_text']
    ordering = ['plan__category', 'display_order', 'plan__duration_days']
    
    def plan_name(self, obj):
        if not obj or not obj.plan:
            return '—'
        return obj.plan.name
    plan_name.short_description = 'Plan'
    plan_name.admin_order_field = 'plan__name'
    
    def plan_category(self, obj):
        if not obj or not obj.plan:
            return '—'
        return obj.plan.get_category_display()
    plan_category.short_description = 'Category'
    plan_category.admin_order_field = 'plan__category'
    
    def custom_badge_display(self, obj):
        if not obj or not getattr(obj, 'custom_badge_text', None):
            return '—'
        return format_html(
            '<span style="background-color: #8b5cf6; color: white; padding: 2px 6px; '
            'border-radius: 8px; font-size: 10px;">{}</span>',
            obj.custom_badge_text
        )
    custom_badge_display.short_description = 'Custom Badge'
    
    actions = ['show_plans', 'hide_plans']
    
    def show_plans(self, request, queryset):
        updated = queryset.update(is_visible=True)
        self.message_user(request, f'{updated} plans are now visible to users.')
    show_plans.short_description = 'Show selected plans to users'
    
    def hide_plans(self, request, queryset):
        updated = queryset.update(is_visible=False)
        self.message_user(request, f'{updated} plans are now hidden from users.')
    hide_plans.short_description = 'Hide selected plans from users'


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'user_link', 'plan_info', 'amount_display', 
        'status_display', 'payment_method', 'created_at'
    ]
    list_filter = [
        'status', 'payment_method', 'plan__category', 'created_at',
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = [
        'transaction_id', 'payu_transaction_id', 'user__username', 
        'user__email', 'user__first_name', 'user__last_name'
    ]
    ordering = ['-created_at']
    readonly_fields = [
        'uid', 'transaction_id', 'payu_transaction_id', 'mihpayid',
        'gateway_response_display', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('user', 'plan', 'amount', 'status', 'payment_method')
        }),
        ('Gateway Information', {
            'fields': (
                'transaction_id', 'payu_transaction_id', 'mihpayid',
                'mode', 'bank_ref_num', 'bankcode'
            ),
            'classes': ('collapse',)
        }),
        ('Failure Information', {
            'fields': ('failure_reason',),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('uid', 'gateway_response_display', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def user_link(self, obj):
        if not obj or not obj.user:
            return '—'
        try:
            url = reverse('admin:auth_user_change', args=[obj.user.pk])
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url, obj.user.username
            )
        except (AttributeError, TypeError):
            return obj.user.username if obj.user else '—'
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'
    
    def plan_info(self, obj):
        if not obj or not obj.plan:
            return '—'
        return format_html(
            '<div style="font-size: 12px;">'
            '<strong>{}</strong><br>'
            '<span style="color: #6b7280;">{}</span>'
            '</div>',
            obj.plan.name,
            obj.plan.get_category_display()
        )
    plan_info.short_description = 'Plan'
    
    def amount_display(self, obj):
        if not obj or obj.amount is None:
            return '—'
        
        color = '#059669' if obj.status == 'success' else '#dc2626' if obj.status == 'failed' else '#f59e0b'
        return format_html(
            '<strong style="color: {};">₹{}</strong>',
            color, obj.amount
        )
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def status_display(self, obj):
        if not obj or not obj.status:
            return '—'
        
        status_colors = {
            'pending': '#f59e0b',
            'success': '#10b981',
            'failed': '#ef4444',
            'cancelled': '#6b7280',
            'refunded': '#8b5cf6'
        }
        color = status_colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; '
            'border-radius: 12px; font-size: 11px; font-weight: bold; text-transform: uppercase;">{}</span>',
            color, obj.status
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    def gateway_response_display(self, obj):
        if not obj or not getattr(obj, 'gateway_response', None):
            return '—'
        try:
            formatted_json = json.dumps(obj.gateway_response, indent=2)
            return format_html(
                '<pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; '
                'font-size: 11px; max-height: 200px; overflow-y: auto;">{}</pre>',
                formatted_json
            )
        except (TypeError, ValueError):
            return '—'
    gateway_response_display.short_description = 'Gateway Response'
    
    actions = ['export_transactions']
    
    def export_transactions(self, request, queryset):
        # You can implement CSV export here
        self.message_user(request, f'{queryset.count()} transactions selected for export.')
    export_transactions.short_description = 'Export selected transactions'
    
    # Add date hierarchy for better navigation
    date_hierarchy = 'created_at'


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'user_link', 'plan_info', 'status_display', 'start_date', 'end_date', 
        'days_remaining_display', 'transaction_link'
    ]
    list_filter = [
        'is_active', 'auto_renewal', 'plan__category', 'plan__plan_type',
        ('start_date', admin.DateFieldListFilter),
        ('end_date', admin.DateFieldListFilter)
    ]
    search_fields = [
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'plan__name', 'transaction__transaction_id'
    ]
    ordering = ['-created_at']
    readonly_fields = [
        'uid', 'created_at', 'updated_at', 'is_expired_display', 'days_remaining_display'
    ]
    
    fieldsets = (
        ('Subscription Details', {
            'fields': ('user', 'plan', 'transaction', 'is_active', 'auto_renewal')
        }),
        ('Duration', {
            'fields': ('start_date', 'end_date', 'is_expired_display', 'days_remaining_display')
        }),
        ('System Information', {
            'fields': ('uid', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def user_link(self, obj):
        if not obj or not obj.user:
            return '—'
        try:
            url = reverse('admin:auth_user_change', args=[obj.user.pk])
            display_name = obj.user.get_full_name() or obj.user.username
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url, display_name
            )
        except (AttributeError, TypeError):
            return obj.user.username if obj.user else '—'
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'
    
    def plan_info(self, obj):
        if not obj or not obj.plan:
            return '—'
        return format_html(
            '<div style="font-size: 12px;">'
            '<strong>{}</strong><br>'
            '<span style="color: #6b7280;">{} • ₹{}</span>'
            '</div>',
            obj.plan.name,
            obj.plan.get_category_display(),
            obj.plan.price or 0
        )
    plan_info.short_description = 'Plan'
    
    def status_display(self, obj):
        if not obj:
            return '—'
        
        try:
            is_expired = getattr(obj, 'is_expired', True)
            is_active = getattr(obj, 'is_active', False)
            
            if is_active and not is_expired:
                status = 'Active'
                color = '#10b981'
            elif is_expired:
                status = 'Expired'
                color = '#ef4444'
            else:
                status = 'Inactive'
                color = '#6b7280'
                
            return format_html(
                '<span style="background-color: {}; color: white; padding: 4px 8px; '
                'border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
                color, status
            )
        except (AttributeError, TypeError):
            return '—'
    status_display.short_description = 'Status'
    
    def days_remaining_display(self, obj):
        if not obj:
            return '—'
        
        try:
            # First try to get days_remaining property
            days = getattr(obj, 'days_remaining', None)
            
            if days is None:
                # Calculate days remaining manually if property doesn't exist
                if not obj.end_date:
                    return '—'
                
                from django.utils import timezone
                current_time = timezone.now()
                
                # Handle timezone-aware comparison
                if hasattr(obj.end_date, 'date'):
                    end_date = obj.end_date.date()
                    current_date = current_time.date()
                else:
                    end_date = obj.end_date
                    current_date = current_time.date()
                
                delta = end_date - current_date
                days = delta.days
            
            if days is None:
                return '—'
                
            days = int(days)  # Ensure it's an integer
            
            if days > 0:
                color = '#10b981' if days > 7 else '#f59e0b' if days > 3 else '#ef4444'
                return format_html(
                    '<span style="color: {}; font-weight: bold;">{} days</span>',
                    color, days
                )
            return format_html('<span style="color: #ef4444;">Expired</span>')
        except (AttributeError, TypeError, ValueError):
            return '—'
    days_remaining_display.short_description = 'Days Left'
    
    def is_expired_display(self, obj):
        if not obj:
            return '—'
        
        try:
            is_expired = getattr(obj, 'is_expired', None)
            if is_expired is None:
                # Calculate if subscription is expired
                if obj.end_date:
                    is_expired = obj.end_date.date() < timezone.now().date()
                else:
                    return '—'
            
            return '✅ Valid' if not is_expired else '❌ Expired'
        except (AttributeError, TypeError):
            return '—'
    is_expired_display.short_description = 'Status'
    
    def transaction_link(self, obj):
        if not obj or not obj.transaction:
            return '—'
        
        try:
            url = reverse('admin:payments_paymenttransaction_change', args=[obj.transaction.pk])
            transaction_id = obj.transaction.transaction_id
            display_id = transaction_id[:20] + '...' if len(transaction_id) > 20 else transaction_id
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url, display_id
            )
        except (AttributeError, TypeError):
            return obj.transaction.transaction_id if obj.transaction else '—'
    transaction_link.short_description = 'Transaction'
    
    actions = ['activate_subscriptions', 'deactivate_subscriptions', 'extend_subscriptions']
    
    def activate_subscriptions(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} subscriptions activated.')
    activate_subscriptions.short_description = 'Activate selected subscriptions'
    
    def deactivate_subscriptions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} subscriptions deactivated.')
    deactivate_subscriptions.short_description = 'Deactivate selected subscriptions'
    
    def extend_subscriptions(self, request, queryset):
        # Add 30 days to end_date
        from django.utils import timezone
        from datetime import timedelta
        
        count = 0
        for subscription in queryset.filter(is_active=True):
            if subscription.end_date:
                subscription.end_date = subscription.end_date + timedelta(days=30)
                subscription.save()
                count += 1
        
        self.message_user(request, f'{count} subscriptions extended by 30 days.')
    extend_subscriptions.short_description = 'Extend selected subscriptions by 30 days'
    
    # Add date hierarchy for better navigation
    date_hierarchy = 'created_at'


# Admin Dashboard Summary
class PaymentAdminSite(admin.AdminSite):
    site_header = 'MCQwave Payment Management'
    site_title = 'Payment Admin'
    index_title = 'Payment Dashboard'
    
    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        # Add dashboard statistics
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        try:
            stats = {
                'total_plans': PaymentPlan.objects.filter(is_active=True).count(),
                'active_subscriptions': UserSubscription.objects.filter(is_active=True).count(),
                'weekly_transactions': PaymentTransaction.objects.filter(
                    created_at__date__gte=week_ago,
                    status='success'
                ).count(),
                'monthly_revenue': PaymentTransaction.objects.filter(
                    created_at__date__gte=month_ago,
                    status='success'
                ).aggregate(Sum('amount'))['amount__sum'] or 0,
            }
        except Exception:
            # Fallback stats if queries fail
            stats = {
                'total_plans': 0,
                'active_subscriptions': 0,
                'weekly_transactions': 0,
                'monthly_revenue': 0,
            }
        
        extra_context['stats'] = stats
        
        return super().index(request, extra_context)

# Uncomment to use custom admin site
# admin_site = PaymentAdminSite(name='payment_admin')